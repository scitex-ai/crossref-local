"""Fast database statistics with an exact-count cache.

``COUNT(*)`` is prohibitively slow on the production database
(measured 2026-07-22: ``works`` 167,008,748 rows -> 0.42 s;
``works_fts`` -> 12.70 s because FTS5 virtual tables scan everything;
``citations`` 1,788,599,072 rows -> 4.35 s; ~17.5 s total per
``info()`` call). ``SELECT MAX(rowid)`` returns the same magnitude in
~0.02 s.

This module keeps ``info()`` O(1):

- :func:`read_cached_counts` reads the ``db_stats`` cache table
  (exact counts written by :func:`refresh_stats`).
- :func:`estimate_counts` returns cheap ``MAX(rowid)`` estimates.
- :func:`get_counts` is the read path: cache first, estimate
  fallback — the result is ALWAYS labelled via ``counts_source``
  (``"exact"`` or ``"estimated"``); an estimate is never silently
  presented as exact, and the read path NEVER runs ``COUNT(*)``.
- :func:`refresh_stats` computes exact ``COUNT(*)`` per table and
  writes the cache. This is the ONLY function that writes; ``info()``
  on a read-only database (no ``db_stats`` table) just estimates.

Cache schema::

    CREATE TABLE db_stats (
        table_name  TEXT PRIMARY KEY,
        row_count   INTEGER,
        computed_at TEXT
    )
"""

import sqlite3 as _sqlite3
from datetime import datetime as _datetime
from datetime import timezone as _timezone
from pathlib import Path as _Path
from typing import Optional as _Optional

from .config import Config as _Config

__all__ = [
    "STATS_TABLES",
    "read_cached_counts",
    "estimate_counts",
    "get_counts",
    "refresh_stats",
]

# (sqlite table, public info() key) pairs — order defines output order.
STATS_TABLES = (
    ("works", "works"),
    ("works_fts", "fts_indexed"),
    ("citations", "citations"),
)


def read_cached_counts(db) -> _Optional[dict]:
    """Read exact counts from the ``db_stats`` cache table.

    Args:
        db: A :class:`crossref_local._core.db.Database` (or any object
            with ``fetchall(query)``).

    Returns:
        ``{"works": n, "fts_indexed": n, "citations": n,
        "counts_computed_at": <ISO timestamp>}`` when the cache covers
        every tracked table, else ``None`` (absent table, unreadable
        row, or partial coverage — the caller then estimates).
    """
    try:
        rows = db.fetchall(
            "SELECT table_name, row_count, computed_at FROM db_stats"
        )
    except Exception:
        return None

    by_table = {row["table_name"]: row for row in rows}
    if any(table not in by_table for table, _key in STATS_TABLES):
        return None

    counts = {}
    computed_stamps = []
    for table, key in STATS_TABLES:
        row = by_table[table]
        row_count = row["row_count"]
        if not isinstance(row_count, int):
            return None
        counts[key] = row_count
        computed_stamps.append(row["computed_at"])

    # Report the OLDEST stamp: the honest age of the least-fresh count.
    counts["counts_computed_at"] = min(
        (s for s in computed_stamps if s), default=None
    )
    return counts


def estimate_counts(db) -> dict:
    """Cheap row-count estimates via ``MAX(rowid)`` (never ``COUNT(*)``).

    ``MAX(rowid)`` is O(1) on rowid tables and equals the row count for
    append-only tables (rowids allocated sequentially, no deletes) —
    which is how the ingest pipeline writes. A table that is absent or
    unreadable reports 0, matching the previous ``info()`` behaviour.
    """
    counts = {}
    for table, key in STATS_TABLES:
        try:
            row = db.fetchone(f"SELECT MAX(rowid) AS n FROM {table}")
            counts[key] = row["n"] if row and row["n"] is not None else 0
        except Exception:
            counts[key] = 0
    counts["counts_computed_at"] = None
    return counts


def get_counts(db) -> dict:
    """Fast, honestly-labelled table counts (the ``info()`` read path).

    Reads the ``db_stats`` cache when present (``counts_source:
    "exact"``); otherwise falls back to ``MAX(rowid)`` estimates
    (``counts_source: "estimated"``). Never runs ``COUNT(*)`` and never
    writes — safe on read-only databases.
    """
    cached = read_cached_counts(db)
    if cached is not None:
        cached["counts_source"] = "exact"
        return cached
    estimated = estimate_counts(db)
    estimated["counts_source"] = "estimated"
    return estimated


def refresh_stats(db_path: _Optional[str | _Path] = None) -> dict:
    """Compute exact ``COUNT(*)`` per table and write the cache.

    Slow by design (~17.5 s on the production database) — run it from
    the ingest/update pipeline or ``crossref-local refresh-stats``, not
    from ``info()``. Requires write access (creates ``db_stats`` if
    absent).

    Args:
        db_path: Database path override; defaults to the configured DB.

    Returns:
        The freshly computed counts, same shape as :func:`get_counts`
        (``counts_source: "exact"``).

    Raises:
        sqlite3.OperationalError: If the database is not writable.
    """
    path = _Path(db_path) if db_path else _Config.get_db_path()
    computed_at = _datetime.now(_timezone.utc).isoformat(timespec="seconds")

    conn = _sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS db_stats ("
            "table_name TEXT PRIMARY KEY, "
            "row_count INTEGER, "
            "computed_at TEXT)"
        )
        counts = {}
        for table, key in STATS_TABLES:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except _sqlite3.OperationalError:
                # Table absent (e.g. minimal DB without citations):
                # record 0 — same convention the old info() used.
                n = 0
            conn.execute(
                "INSERT OR REPLACE INTO db_stats "
                "(table_name, row_count, computed_at) VALUES (?, ?, ?)",
                (table, n, computed_at),
            )
            counts[key] = n
        conn.commit()
    finally:
        conn.close()

    counts["counts_computed_at"] = computed_at
    counts["counts_source"] = "exact"
    return counts

# EOF
