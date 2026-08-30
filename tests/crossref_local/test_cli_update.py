#!/usr/bin/env python3
"""Tests for the incremental ``crossref-local update-db`` command + engine.

These tests NEVER touch the network and never touch the production corpus:
the page fetcher is injected (or supplied through the real
``CROSSREF_LOCAL_UPDATE_FEED`` offline-feed file the engine already
supports), and every write lands in a throwaway schema opened by the
``store_env`` fixture.

The engine used to live at ``scripts/database/10_differential_update.py``
and was loaded here by file path through ``importlib.spec_from_file_location``
— the script is gone and the engine is now an ordinary module, so it is
imported by name like anything else.
"""

import json
import os

import pytest
from click.testing import CliRunner

from crossref_local._core import fts, ingest
from crossref_local._core.store import sync_state_store, works_store
from crossref_local.cli import cli


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


def _work(doi, title="A Title"):
    """Build a minimal CrossRef work item."""
    return {
        "DOI": doi,
        "type": "journal-article",
        "title": [title],
        "author": [{"given": "Ada", "family": "Lovelace"}],
    }


class _PagedFetcher:
    """A page fetcher that serves fixed pages and counts how often it ran.

    Not a mock of the HTTP layer: it is the injection point the engine
    documents (``fetch_page``), holding real page payloads. The call count
    is what makes "stops on a short page WITHOUT a second fetch" assertable
    — an engine that kept paging would ask for a page that does not exist.
    """

    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    def __call__(self, since, cursor, rows, mailto):
        page = self.pages[self.calls]
        self.calls += 1
        return page


@pytest.fixture
def feed_env(tmp_path):
    """Point the real ``update()`` code path at an offline feed file.

    Substitutes reality (a real JSON file read by the engine's own feed
    loader) for the network, so the CLI exercises the true
    ``crossref_local.update`` -> ingest path with no mocks. The env var is
    set here and restored on teardown.
    """
    pages = [{"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": None}]
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps(pages), encoding="utf-8")
    key = "CROSSREF_LOCAL_UPDATE_FEED"
    prior = os.environ.get(key)
    os.environ[key] = str(feed_path)
    try:
        yield feed_path
    finally:
        if prior is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prior


# ---------------------------------------------------------------------------
# Cursor paging
# ---------------------------------------------------------------------------
def test_iter_crossref_works_follows_cursor_across_pages():
    # Arrange
    fetch = _PagedFetcher(
        [
            {"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": "c2"},
            {"items": [_work("10.1/c")], "next-cursor": "c3"},
        ]
    )
    # Act
    dois = [
        work["DOI"]
        for work in ingest.iter_crossref_works(
            since="2026-01-01", rows=2, fetch_page=fetch
        )
    ]
    # Assert
    assert dois == ["10.1/a", "10.1/b", "10.1/c"]


@pytest.fixture
def short_first_page():
    """Drain the iterator over a single short page; return the fetcher."""
    fetch = _PagedFetcher([{"items": [_work("10.1/a")], "next-cursor": "c2"}])
    list(ingest.iter_crossref_works(since="2026-01-01", rows=2, fetch_page=fetch))
    return fetch


def test_iter_crossref_works_stops_on_a_short_page(short_first_page):
    # Arrange
    # Act
    calls = short_first_page.calls
    # Assert — a short page is the deep-paging terminator; asking again
    # would be a wasted round trip (and here, an IndexError).
    assert calls == 1


def test_iter_crossref_works_yields_the_short_page_contents():
    # Arrange
    fetch = _PagedFetcher([{"items": [_work("10.1/a")], "next-cursor": "c2"}])
    # Act
    result = list(
        ingest.iter_crossref_works(since="2026-01-01", rows=2, fetch_page=fetch)
    )
    # Assert
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def test_work_values_lowercases_the_doi():
    # Arrange
    item = _work("10.1/MixedCase")
    # Act
    values = ingest.work_values(item)
    # Assert
    assert values["doi"] == "10.1/mixedcase"


def test_work_values_returns_none_for_an_item_with_no_doi():
    # Arrange — nothing could key it, and inventing a key would put a
    # record in the collection that no lookup could ever find again.
    item = {"title": ["No DOI here"]}
    # Act
    values = ingest.work_values(item)
    # Assert
    assert values is None


def test_work_values_flattens_the_author_list_for_search():
    # Arrange
    item = _work("10.1/a")
    # Act
    values = ingest.work_values(item)
    # Assert
    assert values["authors"] == "Ada Lovelace"


# ---------------------------------------------------------------------------
# Upsert writes records
# ---------------------------------------------------------------------------
@pytest.fixture
def after_two_item_update(store_env):
    """Run the engine over one page of two works."""
    fetch = _PagedFetcher(
        [{"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": None}]
    )
    stats = ingest.differential_update(
        since="2026-01-01", rows=10, fetch_page=fetch, refresh_counts=False
    )
    return stats


def test_update_upserts_one_record_per_work(after_two_item_update):
    # Arrange
    # Act
    rows = works_store().rows()
    # Assert
    assert len(rows) == 2


def test_update_reports_the_number_of_records_upserted(after_two_item_update):
    # Arrange
    # Act
    # Assert
    assert after_two_item_update["records_upserted"] == 2


def test_update_stores_the_searchable_title(after_two_item_update):
    # Arrange
    # Act
    row = works_store().get({"doi": "10.1/a"})
    # Assert
    assert row.values["title"] == "A Title"


@pytest.fixture
def after_resync(store_env):
    """Ingest the same DOI twice."""
    for _attempt in range(2):
        fetch = _PagedFetcher(
            [{"items": [_work("10.1/a")], "next-cursor": None}]
        )
        ingest.differential_update(
            since="2026-01-01", rows=10, fetch_page=fetch, refresh_counts=False
        )
    return store_env


def test_resyncing_the_same_doi_keeps_one_record(after_resync):
    # Arrange — the DOI is the identity, so a re-ingest updates in place.
    # Act
    rows = works_store().rows()
    # Assert
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# An upserted work is immediately searchable
# ---------------------------------------------------------------------------
@pytest.fixture
def after_upserting_neurons(store_env):
    """Ingest one work whose title carries a distinctive term."""
    fetch = _PagedFetcher(
        [{"items": [_work("10.1/a", title="Neurons")], "next-cursor": None}]
    )
    ingest.differential_update(
        since="2026-01-01", rows=10, fetch_page=fetch, refresh_counts=False
    )
    return store_env


def test_an_upserted_work_is_findable_by_search(after_upserting_neurons):
    # Arrange — searchable text is written in the SAME upsert as the rest
    # of the record, so there is no second write that could be skipped.
    # Act
    dois = fts.search_dois("neurons")
    # Assert
    assert dois == ["10.1/a"]


# ---------------------------------------------------------------------------
# The watermark advances only after a successful run
# ---------------------------------------------------------------------------
def test_update_records_the_last_sync_date(after_two_item_update):
    # Arrange
    # Act
    value = ingest.get_last_sync_date()
    # Assert
    assert value is not None


def test_update_records_the_number_of_records_in_sync_state(after_two_item_update):
    # Arrange
    # Act
    row = sync_state_store().get({"key": "last_update_records"})
    # Assert
    assert row.values["value"] == "2"


# ---------------------------------------------------------------------------
# dry-run writes nothing
# ---------------------------------------------------------------------------
@pytest.fixture
def after_dry_run(store_env):
    """Run the engine with ``dry_run=True``."""
    fetch = _PagedFetcher(
        [{"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": None}]
    )
    return ingest.differential_update(
        since="2026-01-01", rows=10, dry_run=True, fetch_page=fetch
    )


def test_dry_run_writes_no_records(after_dry_run):
    # Arrange
    # Act
    rows = works_store().rows()
    # Assert
    assert rows == []


def test_dry_run_still_counts_what_would_be_upserted(after_dry_run):
    # Arrange
    # Act
    # Assert
    assert after_dry_run["records_upserted"] == 2


def test_dry_run_leaves_the_watermark_unset(after_dry_run):
    # Arrange — an interrupted or previewed run must re-cover the same
    # range next time, so it may not advance the watermark.
    # Act
    value = ingest.get_last_sync_date()
    # Assert
    assert value is None


def test_dry_run_labels_itself_in_the_returned_statistics(after_dry_run):
    # Arrange
    # Act
    # Assert
    assert after_dry_run["dry_run"] is True


# ---------------------------------------------------------------------------
# CLI arg wiring + exit codes
# ---------------------------------------------------------------------------
def test_cli_update_help_exits_zero(runner):
    # Arrange
    args = ["update-db", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


def test_cli_update_help_lists_since_option(runner):
    # Arrange
    args = ["update-db", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert "--since" in result.output


@pytest.fixture
def cli_dry_run(runner, store_env, feed_env):
    """Drive the CLI's dry-run path over the offline feed."""
    return runner.invoke(
        cli, ["update-db", "--dry-run", "--since", "2026-01-01"]
    )


def test_cli_update_dry_run_exits_zero(cli_dry_run):
    # Arrange
    # Act
    # Assert
    assert cli_dry_run.exit_code == 0, cli_dry_run.output


def test_cli_update_dry_run_writes_no_records(cli_dry_run):
    # Arrange
    # Act
    rows = works_store().rows()
    # Assert
    assert rows == []


@pytest.fixture
def cli_real_run(runner, store_env, feed_env):
    """Drive the CLI's real (``--yes``) path over the offline feed."""
    return runner.invoke(
        cli, ["update-db", "--yes", "--since", "2026-01-01"]
    )


def test_cli_update_yes_upserts_the_feed(cli_real_run):
    # Arrange
    # Act
    rows = works_store().rows()
    # Assert
    assert len(rows) == 2


def test_cli_update_yes_exits_zero(cli_real_run):
    # Arrange
    # Act
    # Assert
    assert cli_real_run.exit_code == 0, cli_real_run.output


def test_cli_update_quiet_prints_a_one_line_summary(runner, store_env, feed_env):
    # Arrange — assert on STDOUT, not on ``output``: click 8.5 merges
    # stderr into ``output``, and the SciTeX logging runtime installs a
    # root INFO handler on stderr, so ``output`` carries the engine's
    # progress lines too. What ``--quiet`` promises a cron job is that
    # STDOUT is the single summary line.
    args = ["update-db", "--yes", "--quiet", "--since", "2026-01-01"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.stdout.strip().startswith("2 ")


@pytest.fixture
def cli_without_yes(runner, store_env, feed_env):
    """Invoke the mutating command with no ``--yes``."""
    return runner.invoke(cli, ["update-db", "--since", "2026-01-01"])


def test_cli_update_db_refuses_without_yes(cli_without_yes):
    # Arrange — §2 non-interactive contract: a real run without --yes must
    # refuse (exit 2), never prompt.
    # Act
    # Assert
    assert cli_without_yes.exit_code == 2


def test_cli_update_db_refusal_mentions_the_yes_flag(cli_without_yes):
    # Arrange
    # Act
    # Assert
    assert "--yes" in cli_without_yes.output


def test_cli_update_db_refusal_writes_nothing(cli_without_yes):
    # Arrange
    # Act
    rows = works_store().rows()
    # Assert
    assert rows == []


def test_cli_deprecated_update_alias_still_works(runner, store_env, feed_env):
    # Arrange — Phase-W alias: old `update` spelling forwards to
    # `update-db` (the dry-run path needs no --yes).
    args = ["update", "--dry-run", "--since", "2026-01-01"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0, result.output


# EOF
