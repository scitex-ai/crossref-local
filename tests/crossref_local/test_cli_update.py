#!/usr/bin/env python3
"""Tests for the incremental ``crossref-local update-db`` command + engine.

These tests NEVER touch the network or the ~1.5 TB CrossRef DB: the sync
engine's HTTP fetcher is injected with a fake page-feed, and all writes
go to a tiny temp SQLite carrying only the minimal ``works`` / ``_metadata``
/ ``works_fts`` schema.
"""

import importlib.util
import json
import os
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from crossref_local.cli import cli

# ---------------------------------------------------------------------------
# Load the sync engine by file path (it lives under scripts/, not the package).
# ---------------------------------------------------------------------------
_ENGINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "database"
    / "10_differential_update.py"
)
_spec = importlib.util.spec_from_file_location("_diff_update_engine", _ENGINE_PATH)
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_db(tmp_path):
    """Create a tiny SQLite with the minimal works/FTS/metadata schema."""
    db_path = tmp_path / "crossref.db"
    conn = sqlite3.connect(str(db_path))
    try:
        engine.ensure_metadata_table(conn)
        engine.create_works_table(conn.cursor())
        conn.execute(
            "CREATE VIRTUAL TABLE works_fts USING fts5("
            "doi, title, abstract, authors, content='')"
        )
        conn.commit()
    finally:
        conn.close()
    yield db_path


def _work(doi, title="A Title"):
    """Build a minimal CrossRef work item."""
    return {
        "DOI": doi,
        "type": "journal-article",
        "title": [title],
        "author": [{"given": "Ada", "family": "Lovelace"}],
    }


@pytest.fixture
def feed_env(tmp_path):
    """Point the real ``update()`` code path at an offline feed + script.

    Substitutes reality (real JSON file + real env vars) for the network
    so the CLI exercises the true ``crossref_local.update`` -> engine path
    with no mocks:

    * ``CROSSREF_LOCAL_UPDATE_FEED`` — a JSON list of API pages served in
      place of the network fetch.
    * ``CROSSREF_LOCAL_DIFFERENTIAL_UPDATE_SCRIPT`` — pins the engine to
      THIS worktree's script regardless of where the package is installed.

    Both env vars are set here and popped on teardown.
    """
    pages = [{"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": None}]
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps(pages), encoding="utf-8")
    keys = {
        "CROSSREF_LOCAL_UPDATE_FEED": str(feed_path),
        "CROSSREF_LOCAL_DIFFERENTIAL_UPDATE_SCRIPT": str(_ENGINE_PATH),
    }
    prior = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    try:
        yield feed_path
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _paged_fetcher(pages):
    """Return a fake ``fetch_page`` yielding the given pages by cursor.

    ``pages`` is a list of message dicts; each is returned in order,
    advancing the cursor so deep-paging terminates on the last (short) page.
    """
    state = {"i": 0}

    def fetch(since, cursor, rows, mailto):
        idx = state["i"]
        state["i"] += 1
        return pages[idx]

    return fetch


# ---------------------------------------------------------------------------
# Cursor paging
# ---------------------------------------------------------------------------
def test_iter_crossref_works_follows_cursor_across_pages():
    # Arrange
    pages = [
        {"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": "c2"},
        {"items": [_work("10.1/c")], "next-cursor": "c3"},
    ]
    fetch = _paged_fetcher(pages)
    # Act
    dois = [
        w["DOI"]
        for w in engine.iter_crossref_works(
            since="2026-01-01", rows=2, fetch_page=fetch
        )
    ]
    # Assert
    assert dois == ["10.1/a", "10.1/b", "10.1/c"]


def test_iter_crossref_works_stops_on_short_page():
    # Arrange — a single short page must end paging without a 2nd fetch.
    pages = [{"items": [_work("10.1/a")], "next-cursor": "c2"}]
    fetch = _paged_fetcher(pages)
    # Act
    result = list(
        engine.iter_crossref_works(since="2026-01-01", rows=2, fetch_page=fetch)
    )
    # Assert
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Upsert writes rows
# ---------------------------------------------------------------------------
def test_update_upserts_rows_into_works(temp_db):
    # Arrange
    pages = [{"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": None}]
    fetch = _paged_fetcher(pages)
    # Act
    engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10, fetch_page=fetch
    )
    # Assert
    conn = sqlite3.connect(str(temp_db))
    count = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    conn.close()
    assert count == 2


def test_update_reports_records_upserted(temp_db):
    # Arrange
    pages = [{"items": [_work("10.1/a")], "next-cursor": None}]
    fetch = _paged_fetcher(pages)
    # Act
    stats = engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10, fetch_page=fetch
    )
    # Assert
    assert stats["records_upserted"] == 1


def test_update_is_idempotent_on_resync(temp_db):
    # Arrange — same DOI seen twice must not create a duplicate row.
    page = [{"items": [_work("10.1/a")], "next-cursor": None}]
    engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10,
        fetch_page=_paged_fetcher([dict(page[0])]),
    )
    # Act
    engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10,
        fetch_page=_paged_fetcher([dict(page[0])]),
    )
    # Assert
    conn = sqlite3.connect(str(temp_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM works WHERE doi = '10.1/a'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_update_maintains_fts_index(temp_db):
    # Arrange
    pages = [{"items": [_work("10.1/a", title="Neurons")], "next-cursor": None}]
    fetch = _paged_fetcher(pages)
    engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10, fetch_page=fetch
    )
    # Act
    conn = sqlite3.connect(str(temp_db))
    hits = conn.execute(
        "SELECT COUNT(*) FROM works_fts WHERE works_fts MATCH 'Neurons'"
    ).fetchone()[0]
    conn.close()
    # Assert
    assert hits == 1


# ---------------------------------------------------------------------------
# last_sync_date advances only after success
# ---------------------------------------------------------------------------
def test_update_advances_last_sync_date(temp_db):
    # Arrange
    pages = [{"items": [_work("10.1/a")], "next-cursor": None}]
    fetch = _paged_fetcher(pages)
    # Act
    engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10, fetch_page=fetch
    )
    # Assert
    conn = sqlite3.connect(str(temp_db))
    value = engine.get_last_sync_date(conn)
    conn.close()
    assert value is not None


# ---------------------------------------------------------------------------
# dry-run writes nothing
# ---------------------------------------------------------------------------
def test_dry_run_writes_no_rows(temp_db):
    # Arrange
    pages = [{"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": None}]
    fetch = _paged_fetcher(pages)
    # Act
    engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10,
        dry_run=True, fetch_page=fetch,
    )
    # Assert
    conn = sqlite3.connect(str(temp_db))
    count = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    conn.close()
    assert count == 0


def test_dry_run_counts_would_be_upserts(temp_db):
    # Arrange
    pages = [{"items": [_work("10.1/a"), _work("10.1/b")], "next-cursor": None}]
    fetch = _paged_fetcher(pages)
    # Act
    stats = engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10,
        dry_run=True, fetch_page=fetch,
    )
    # Assert
    assert stats["records_upserted"] == 2


def test_dry_run_leaves_last_sync_date_unset(temp_db):
    # Arrange
    pages = [{"items": [_work("10.1/a")], "next-cursor": None}]
    fetch = _paged_fetcher(pages)
    # Act
    engine.differential_update(
        db_path=temp_db, since="2026-01-01", rows=10,
        dry_run=True, fetch_page=fetch,
    )
    # Assert
    conn = sqlite3.connect(str(temp_db))
    value = engine.get_last_sync_date(conn)
    conn.close()
    assert value is None


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


def test_cli_update_dry_run_exits_zero(runner, temp_db, feed_env):
    # Arrange — real code path: offline feed + real temp DB, no network.
    args = ["update-db", "--db", str(temp_db), "--dry-run", "--since", "2026-01-01"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


def test_cli_update_dry_run_writes_no_rows(runner, temp_db, feed_env):
    # Arrange
    args = ["update-db", "--db", str(temp_db), "--dry-run", "--since", "2026-01-01"]
    # Act
    runner.invoke(cli, args)
    # Assert
    conn = sqlite3.connect(str(temp_db))
    count = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    conn.close()
    assert count == 0


def test_cli_update_yes_upserts_rows(runner, temp_db, feed_env):
    # Arrange — --yes runs unattended against the real engine + feed.
    args = ["update-db", "--db", str(temp_db), "--yes", "--since", "2026-01-01"]
    # Act
    runner.invoke(cli, args)
    # Assert
    conn = sqlite3.connect(str(temp_db))
    count = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    conn.close()
    assert count == 2


def test_cli_update_quiet_prints_one_line_summary(runner, temp_db, feed_env):
    # Arrange
    args = [
        "update-db", "--db", str(temp_db),
        "--yes", "--quiet", "--since", "2026-01-01",
    ]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.output.strip().startswith("2 ")


def test_cli_update_reports_nonzero_exit_on_error(runner, tmp_path, feed_env):
    # Arrange — a bad script path makes the real update() raise; the CLI
    # must surface that as a nonzero exit (no mocks, real error path).
    os.environ["CROSSREF_LOCAL_DIFFERENTIAL_UPDATE_SCRIPT"] = str(
        tmp_path / "does_not_exist.py"
    )
    try:
        args = ["update-db", "--db", str(tmp_path / "x.db"), "--yes"]
        # Act
        result = runner.invoke(cli, args)
    finally:
        os.environ.pop("CROSSREF_LOCAL_DIFFERENTIAL_UPDATE_SCRIPT", None)
    # Assert
    assert result.exit_code != 0


def test_cli_update_db_refuses_without_yes(runner, temp_db, feed_env):
    # Arrange — §2 non-interactive contract: a real run without --yes
    # must refuse (exit 2), never prompt.
    args = ["update-db", "--db", str(temp_db), "--since", "2026-01-01"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 2


def test_cli_update_db_refusal_mentions_yes_flag(runner, temp_db, feed_env):
    # Arrange
    args = ["update-db", "--db", str(temp_db), "--since", "2026-01-01"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert "--yes" in result.output


def test_cli_deprecated_update_alias_still_works(runner, temp_db, feed_env):
    # Arrange — Phase-W alias: old `update` spelling forwards to
    # `update-db` (dry-run path needs no --yes).
    args = ["update", "--db", str(temp_db), "--dry-run", "--since", "2026-01-01"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


# EOF
