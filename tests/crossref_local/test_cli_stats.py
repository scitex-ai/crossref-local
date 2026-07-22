#!/usr/bin/env python3
"""Tests for the ``crossref-local sync-stats`` command (_cli/stats.py).

Self-contained: builds a tiny SQLite DB per test (no shared fixture DB
needed — module is listed in ``_DB_OPTIONAL_TEST_MODULES``).
"""

import json
import sqlite3

import pytest
from click.testing import CliRunner

from crossref_local.cli import cli


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def mini_db(tmp_path):
    """Create a minimal works/works_fts/citations SQLite DB."""
    path = tmp_path / "mini.db"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE works (id INTEGER PRIMARY KEY, doi TEXT)")
        conn.execute("INSERT INTO works (doi) VALUES ('10.1/a'), ('10.1/b')")
        conn.execute("CREATE VIRTUAL TABLE works_fts USING fts5(title)")
        conn.execute("INSERT INTO works_fts (title) VALUES ('t1')")
        conn.execute("CREATE TABLE citations (citing_doi TEXT, cited_doi TEXT)")
        conn.commit()
    finally:
        conn.close()
    yield path


def test_cli_sync_stats_help_exits_zero(runner):
    # Arrange
    args = ["sync-stats", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


def test_cli_sync_stats_help_mentions_db_stats_cache(runner):
    # Arrange
    args = ["sync-stats", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert "db_stats" in result.output


def test_cli_sync_stats_exits_zero_on_mini_db(runner, mini_db):
    # Arrange
    args = ["sync-stats", "--yes", "--db", str(mini_db)]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


def test_cli_sync_stats_writes_exact_cache(runner, mini_db):
    # Arrange
    args = ["sync-stats", "--yes", "--db", str(mini_db)]
    # Act
    runner.invoke(cli, args)
    # Assert
    conn = sqlite3.connect(str(mini_db))
    row = conn.execute(
        "SELECT row_count FROM db_stats WHERE table_name = 'works'"
    ).fetchone()
    conn.close()
    assert row[0] == 2


def test_cli_sync_stats_json_reports_exact_source(runner, mini_db):
    # Arrange
    args = ["sync-stats", "--yes", "--db", str(mini_db), "--json"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert json.loads(result.output)["counts_source"] == "exact"


def test_cli_sync_stats_refuses_without_yes(runner, mini_db):
    # Arrange — §2 non-interactive contract: a real run without --yes
    # must refuse (exit 2), never prompt.
    args = ["sync-stats", "--db", str(mini_db)]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 2


def test_cli_sync_stats_dry_run_writes_nothing(runner, mini_db):
    # Arrange
    args = ["sync-stats", "--dry-run", "--db", str(mini_db)]
    # Act
    result = runner.invoke(cli, args)
    # Assert — no db_stats table created and exit 0
    conn = sqlite3.connect(str(mini_db))
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='db_stats'"
    ).fetchone()
    conn.close()
    assert result.exit_code == 0 and row is None


def test_cli_deprecated_refresh_stats_alias_still_works(runner, mini_db):
    # Arrange — Phase-W alias: old `refresh-stats` spelling forwards.
    args = ["refresh-stats", "--yes", "--db", str(mini_db)]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


def test_cli_deprecated_skills_alias_group_still_resolves(runner):
    # Arrange — `skills` moved to `dev skills` (§13); the hidden
    # top-level group must still answer.
    args = ["skills", "--help"]
    # Act
    result = runner.invoke(cli, args)
    # Assert
    assert result.exit_code == 0


# EOF
