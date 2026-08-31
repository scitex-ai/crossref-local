#!/usr/bin/env python3
"""Tests for the ``crossref-local sync-stats`` command (_cli/stats.py).

Self-provisioning: the ``store_env`` fixture points the package's own store
resolution at a throwaway schema, so the command writes its cache there and
nowhere else. There is no ``--db`` path to pass any more — the store is
chosen by resolution, not by an argument — so the command is exercised
exactly as a cron job would invoke it.
"""

import json

import pytest
from click.testing import CliRunner

from crossref_local.cli import cli
from crossref_local._core.store import corpus_stats_store, works_store

#: Works written before the command runs, so "exact" has a value to be.
_WORKS = ("10.1000/stats.a", "10.1000/stats.b")


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def seeded(store_env):
    """Write a couple of works into the throwaway store."""
    from scitex_dev.store import NEW_RECORD

    store = works_store()
    for doi in _WORKS:
        store.put(
            {"doi": doi, "title": f"Title for {doi}"},
            expected_revision=NEW_RECORD,
        )
    return store_env


# ---------- --help ----------


def test_cli_sync_stats_help_exits_zero(runner):
    # Arrange
    args = ["sync-stats", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


def test_cli_sync_stats_help_describes_the_count_cache(runner):
    # Arrange
    args = ["sync-stats", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert "count" in result.output.lower()


def test_cli_sync_stats_help_lists_the_dry_run_option(runner):
    # Arrange
    args = ["sync-stats", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert "--dry-run" in result.output


# ---------- a real run ----------


@pytest.fixture
def after_sync(runner, seeded):
    """Run ``sync-stats --yes`` against the throwaway store."""
    return runner.invoke(cli, ["sync-stats", "--yes"])


def test_cli_sync_stats_exits_zero(after_sync):
    # Arrange
    # Act
    # Assert
    assert after_sync.exit_code == 0, after_sync.output


def test_cli_sync_stats_writes_the_exact_works_count(after_sync):
    # Arrange
    # Act
    row = corpus_stats_store().get({"collection": "works"})
    # Assert
    assert row.values["row_count"] == len(_WORKS)


def test_cli_sync_stats_json_reports_the_source_as_exact(runner, seeded):
    # Arrange
    args = ["sync-stats", "--yes", "--json"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert json.loads(result.output)["counts_source"] == "exact"


def test_cli_sync_stats_json_reports_the_exact_works_count(runner, seeded):
    # Arrange
    args = ["sync-stats", "--yes", "--json"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert json.loads(result.output)["works"] == len(_WORKS)


# ---------- refusal without --yes ----------


@pytest.fixture
def without_yes(runner, seeded):
    """Invoke the mutating command with no ``--yes``."""
    return runner.invoke(cli, ["sync-stats"])


def test_cli_sync_stats_refuses_without_yes(without_yes):
    # Arrange — §2 non-interactive contract: a real run without --yes must
    # refuse (exit 2), never prompt.
    # Act
    # Assert
    assert without_yes.exit_code == 2


def test_cli_sync_stats_refusal_writes_no_cache(without_yes):
    # Arrange
    # Act
    rows = corpus_stats_store().rows()
    # Assert
    assert rows == []


# ---------- --dry-run ----------


@pytest.fixture
def after_dry_run(runner, seeded):
    """Run ``sync-stats --dry-run`` against the throwaway store."""
    return runner.invoke(cli, ["sync-stats", "--dry-run"])


def test_cli_sync_stats_dry_run_exits_zero(after_dry_run):
    # Arrange
    # Act
    # Assert
    assert after_dry_run.exit_code == 0, after_dry_run.output


def test_cli_sync_stats_dry_run_writes_nothing(after_dry_run):
    # Arrange
    # Act
    rows = corpus_stats_store().rows()
    # Assert
    assert rows == []


# ---------- deprecated aliases ----------


def test_cli_deprecated_refresh_stats_alias_still_works(runner, seeded):
    # Arrange — Phase-W alias: old `refresh-stats` spelling forwards.
    args = ["refresh-stats", "--yes"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0, result.output


def test_cli_deprecated_skills_alias_group_still_resolves(runner):
    # Arrange — `skills` moved to `dev skills` (§13); the hidden
    # top-level group must still answer.
    args = ["skills", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


# EOF
