"""
Async API for crossref_local.

Provides async versions of all API functions. Uses thread pool execution
with per-thread database connections for thread safety.

Usage:
    from crossref_local import aio

    async def main():
        results = await aio.search("machine learning")
        work = await aio.get("10.1038/nature12373")
        n = await aio.count("CRISPR")

    # Or import individual functions
    from crossref_local.aio import search, get, count

    # Concurrent operations
    counts = await aio.count_many(["CRISPR", "machine learning"])
"""

import asyncio as _asyncio
import threading as _threading
from typing import List, Optional

from .._core.config import Config as _Config
from .._core.db import Database as _Database
from .._core.models import SearchResult, Work

__all__ = [
    "search",
    "count",
    "get",
    "get_many",
    "exists",
    "info",
    "search_many",
    "count_many",
    # Public types for type hints
    "SearchResult",
    "Work",
]

# Thread-local storage for database connections
_thread_local = _threading.local()


def _get_thread_db() -> _Database:
    """Get thread-local database connection."""
    if not hasattr(_thread_local, "db"):
        _thread_local.db = _Database(_Config.get_db_path())
    return _thread_local.db


def _search_sync(query: str, limit: int, offset: int) -> SearchResult:
    """Thread-safe sync search."""
    from .._core import fts

    db = _get_thread_db()
    return fts._search_with_db(db, query, limit, offset)


def _count_sync(query: str) -> int:
    """Thread-safe sync count."""
    from .._core import fts

    db = _get_thread_db()
    return fts._count_with_db(db, query)


def _get_sync(doi: str) -> Optional[Work]:
    """Thread-safe sync get."""
    db = _get_thread_db()
    metadata = db.get_metadata(doi)
    if metadata:
        return Work.from_metadata(doi, metadata)
    return None


def _get_many_sync(dois: List[str]) -> List[Work]:
    """Thread-safe sync get_many."""
    db = _get_thread_db()
    works = []
    for doi in dois:
        metadata = db.get_metadata(doi)
        if metadata:
            works.append(Work.from_metadata(doi, metadata))
    return works


def _exists_sync(doi: str) -> bool:
    """Thread-safe sync exists."""
    db = _get_thread_db()
    row = db.fetchone("SELECT 1 FROM works WHERE doi = ?", (doi,))
    return row is not None


def _info_sync() -> dict:
    """Thread-safe sync info.

    Counts come from the ``db_stats`` cache (exact) or ``MAX(rowid)``
    estimates — never ``COUNT(*)`` full scans. See ``_core/stats.py``.
    """
    from .._core.stats import get_counts as _get_counts

    db = _get_thread_db()
    return {
        "db_path": str(_Config.get_db_path()),
        **_get_counts(db),
    }


async def search(
    query: str,
    limit: int = 10,
    offset: int = 0,
) -> SearchResult:
    """
    Async full-text search across works.

    Args:
        query: Search query (supports FTS5 syntax)
        limit: Maximum results to return
        offset: Skip first N results (for pagination)

    Returns:
        SearchResult with matching works
    """
    return await _asyncio.to_thread(_search_sync, query, limit, offset)


async def count(query: str) -> int:
    """
    Async count matching works without fetching results.

    Args:
        query: FTS5 search query

    Returns:
        Number of matching works
    """
    return await _asyncio.to_thread(_count_sync, query)


async def get(doi: str) -> Optional[Work]:
    """
    Async get a work by DOI.

    Args:
        doi: Digital Object Identifier

    Returns:
        Work object or None if not found
    """
    return await _asyncio.to_thread(_get_sync, doi)


async def get_many(dois: List[str]) -> List[Work]:
    """
    Async get multiple works by DOI.

    Args:
        dois: List of DOIs

    Returns:
        List of Work objects (missing DOIs are skipped)
    """
    return await _asyncio.to_thread(_get_many_sync, dois)


async def exists(doi: str) -> bool:
    """
    Async check if a DOI exists in the database.

    Args:
        doi: Digital Object Identifier

    Returns:
        True if DOI exists
    """
    return await _asyncio.to_thread(_exists_sync, doi)


async def info() -> dict:
    """
    Async get database information.

    Returns:
        Dictionary with database stats
    """
    return await _asyncio.to_thread(_info_sync)


async def search_many(queries: List[str], limit: int = 10) -> List[SearchResult]:
    """
    Run multiple searches concurrently.

    Args:
        queries: List of search queries
        limit: Maximum results per query

    Returns:
        List of SearchResult objects
    """
    tasks = [search(q, limit=limit) for q in queries]
    return await _asyncio.gather(*tasks)


async def count_many(queries: List[str]) -> dict:
    """
    Count matches for multiple queries concurrently.

    Args:
        queries: List of search queries

    Returns:
        Dict mapping query -> count

    Example:
        >>> counts = await count_many(["CRISPR", "machine learning"])
        >>> print(counts)
        {'CRISPR': 45000, 'machine learning': 477922}
    """
    tasks = [count(q) for q in queries]
    results = await _asyncio.gather(*tasks)
    return dict(zip(queries, results))
