"""Tests for crossref_local._core.stats (db_stats cache + estimates).

These tests build their own tiny SQLite databases, so they run without
the shared fixture/production database (module is listed in
``_DB_OPTIONAL_TEST_MODULES`` in ``tests/conftest.py``).
"""

import os
import sqlite3

import pytest

from crossref_local._core.db import Database, close_db
from crossref_local._core.config import Config
from crossref_local._core.stats import (
    estimate_counts,
    get_counts,
    read_cached_counts,
    refresh_stats,
)

WORKS_ROWS = 5
FTS_ROWS = 3
CITATION_ROWS = 7


@pytest.fixture
def tmp_db(tmp_path):
    """Create a small crossref-shaped SQLite DB (no db_stats table)."""
    path = tmp_path / "mini_crossref.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE works (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "doi VARCHAR(255), metadata BLOB)"
    )
    for i in range(WORKS_ROWS):
        conn.execute(
            "INSERT INTO works (doi, metadata) VALUES (?, ?)",
            (f"10.1234/work{i}", "{}"),
        )
    conn.execute(
        "CREATE VIRTUAL TABLE works_fts USING fts5(title, abstract)"
    )
    for i in range(FTS_ROWS):
        conn.execute(
            "INSERT INTO works_fts (title, abstract) VALUES (?, ?)",
            (f"title {i}", f"abstract {i}"),
        )
    conn.execute(
        "CREATE TABLE citations (citing_doi TEXT, cited_doi TEXT)"
    )
    for i in range(CITATION_ROWS):
        conn.execute(
            "INSERT INTO citations (citing_doi, cited_doi) VALUES (?, ?)",
            (f"10.1234/work{i % WORKS_ROWS}", "10.1234/work0"),
        )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def db(tmp_db):
    """Open the mini DB through the package's Database wrapper."""
    database = Database(tmp_db)
    yield database
    database.close()


@pytest.fixture
def configured_info(tmp_db):
    """Point the package-level info() at the mini DB; restore afterwards."""
    import crossref_local

    crossref_local.configure(str(tmp_db))
    yield crossref_local.info
    Config.reset()
    close_db()


# ---------- estimate path (no cache) ----------


def test_get_counts_without_cache_labels_source_estimated(db):
    # Arrange
    # Act
    counts = get_counts(db)
    # Assert
    assert counts["counts_source"] == "estimated"


def test_get_counts_without_cache_reports_works_via_max_rowid(db):
    # Arrange
    # Act
    counts = get_counts(db)
    # Assert
    assert counts["works"] == WORKS_ROWS


def test_get_counts_without_cache_reports_fts_indexed(db):
    # Arrange
    # Act
    counts = get_counts(db)
    # Assert
    assert counts["fts_indexed"] == FTS_ROWS


def test_get_counts_without_cache_reports_citations(db):
    # Arrange
    # Act
    counts = get_counts(db)
    # Assert
    assert counts["citations"] == CITATION_ROWS


def test_get_counts_without_cache_never_creates_db_stats_table(tmp_db, db):
    # Arrange
    # Act
    get_counts(db)
    # Assert — the read path must not write (read-only deployments)
    conn = sqlite3.connect(str(tmp_db))
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='db_stats'"
    ).fetchone()
    conn.close()
    assert row is None


def test_get_counts_on_readonly_db_file_still_estimates(tmp_db):
    # Arrange
    os.chmod(tmp_db, 0o444)
    database = Database(tmp_db)
    # Act
    counts = get_counts(database)
    # Assert
    database.close()
    os.chmod(tmp_db, 0o644)
    assert counts["works"] == WORKS_ROWS


def test_estimate_after_deletes_keeps_estimated_label(tmp_db, db):
    # Arrange — deletes make MAX(rowid) diverge from COUNT(*), which is
    # exactly why the label must say "estimated"
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("DELETE FROM works WHERE id = 2")
    conn.commit()
    conn.close()
    # Act
    counts = estimate_counts(db)
    # Assert — MAX(rowid) still reports the old magnitude
    assert counts["works"] == WORKS_ROWS


def test_read_cached_counts_returns_none_without_cache(db):
    # Arrange
    # Act
    cached = read_cached_counts(db)
    # Assert
    assert cached is None


def test_read_cached_counts_returns_none_on_partial_cache(tmp_db, db):
    # Arrange — cache row for only ONE of the three tracked tables
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        "CREATE TABLE db_stats (table_name TEXT PRIMARY KEY, "
        "row_count INTEGER, computed_at TEXT)"
    )
    conn.execute(
        "INSERT INTO db_stats VALUES ('works', 5, '2026-07-22T00:00:00')"
    )
    conn.commit()
    conn.close()
    # Act
    cached = read_cached_counts(db)
    # Assert — partial coverage falls back to estimates entirely
    assert cached is None


# ---------- refresh_stats() ----------


def test_refresh_stats_creates_db_stats_table(tmp_db):
    # Arrange
    # Act
    refresh_stats(db_path=tmp_db)
    # Assert
    conn = sqlite3.connect(str(tmp_db))
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='db_stats'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_refresh_stats_returns_exact_works_count(tmp_db):
    # Arrange
    # Act
    counts = refresh_stats(db_path=tmp_db)
    # Assert
    assert counts["works"] == WORKS_ROWS


def test_refresh_stats_returns_exact_fts_count(tmp_db):
    # Arrange
    # Act
    counts = refresh_stats(db_path=tmp_db)
    # Assert
    assert counts["fts_indexed"] == FTS_ROWS


def test_refresh_stats_returns_exact_citations_count(tmp_db):
    # Arrange
    # Act
    counts = refresh_stats(db_path=tmp_db)
    # Assert
    assert counts["citations"] == CITATION_ROWS


def test_refresh_stats_labels_source_exact(tmp_db):
    # Arrange
    # Act
    counts = refresh_stats(db_path=tmp_db)
    # Assert
    assert counts["counts_source"] == "exact"


def test_refresh_stats_records_computed_at_timestamp(tmp_db):
    # Arrange
    # Act
    counts = refresh_stats(db_path=tmp_db)
    # Assert
    assert counts["counts_computed_at"] is not None


def test_refresh_stats_reflects_deletes_exactly(tmp_db):
    # Arrange
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("DELETE FROM works WHERE id = 2")
    conn.commit()
    conn.close()
    # Act
    counts = refresh_stats(db_path=tmp_db)
    # Assert — COUNT(*) sees the delete (MAX(rowid) would not)
    assert counts["works"] == WORKS_ROWS - 1


def test_refresh_stats_records_zero_for_missing_citations_table(tmp_path):
    # Arrange — minimal DB without a citations table
    path = tmp_path / "no_citations.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE works (id INTEGER PRIMARY KEY, doi TEXT)")
    conn.execute("CREATE VIRTUAL TABLE works_fts USING fts5(title)")
    conn.commit()
    conn.close()
    # Act
    counts = refresh_stats(db_path=path)
    # Assert
    assert counts["citations"] == 0


# ---------- cache read path ----------


def test_get_counts_with_cache_labels_source_exact(tmp_db, db):
    # Arrange
    refresh_stats(db_path=tmp_db)
    # Act
    counts = get_counts(db)
    # Assert
    assert counts["counts_source"] == "exact"


def test_get_counts_with_cache_returns_cached_values_not_recomputed(
    tmp_db, db
):
    # Arrange — plant a sentinel value directly in the cache
    refresh_stats(db_path=tmp_db)
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        "UPDATE db_stats SET row_count = 424242 WHERE table_name = 'works'"
    )
    conn.commit()
    conn.close()
    # Act
    counts = get_counts(db)
    # Assert — the cache is READ, never recomputed on this path
    assert counts["works"] == 424242


def test_get_counts_with_cache_reports_computed_at(tmp_db, db):
    # Arrange
    refresh_stats(db_path=tmp_db)
    # Act
    counts = get_counts(db)
    # Assert
    assert counts["counts_computed_at"] is not None


# ---------- info() end-to-end (DB mode) ----------


def test_info_without_cache_labels_counts_estimated(configured_info):
    # Arrange
    # Act
    result = configured_info()
    # Assert
    assert result["counts_source"] == "estimated"


def test_info_without_cache_reports_estimated_works(configured_info):
    # Arrange
    # Act
    result = configured_info()
    # Assert
    assert result["works"] == WORKS_ROWS


def test_info_keeps_backward_compatible_keys(configured_info):
    # Arrange
    # Act
    result = configured_info()
    # Assert
    assert {"works", "fts_indexed", "citations", "mode", "status",
            "db_path"} <= set(result)


def test_info_with_cache_labels_counts_exact(tmp_db, configured_info):
    # Arrange
    refresh_stats(db_path=tmp_db)
    close_db()  # drop the thread-local connection so the cache is seen
    # Act
    result = configured_info()
    # Assert
    assert result["counts_source"] == "exact"


def test_info_with_cache_reports_exact_citations(tmp_db, configured_info):
    # Arrange
    refresh_stats(db_path=tmp_db)
    close_db()
    # Act
    result = configured_info()
    # Assert
    assert result["citations"] == CITATION_ROWS

# EOF
