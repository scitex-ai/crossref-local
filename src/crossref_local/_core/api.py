"""Main API for crossref_local.

Supports two modes:
- db: Direct database access (requires database file)
- http: HTTP API access (requires API server)

Mode is auto-detected or can be set explicitly via:
- CROSSREF_LOCAL_MODE environment variable ("db" or "http")
- CROSSREF_LOCAL_API_URL environment variable (API URL)
- configure() or configure_http() functions
"""

from typing import List, Optional

from . import fts, stats
from .config import Config
from .db import close_db, get_db
from .models import SearchResult, Work
from .stats import refresh_stats

__all__ = [
    "search",
    "count",
    "get",
    "get_many",
    "exists",
    "configure",
    "configure_http",
    "configure_remote",
    "enrich",
    "enrich_dois",
    "get_mode",
    "info",
    "refresh_stats",
    # Re-exported for convenience
    "Work",
    "SearchResult",
    "Config",
]


def _get_http_client():
    """Get HTTP client (lazy import to avoid circular dependency)."""
    from .._remote import RemoteClient  # Uses enhanced client with collections

    return RemoteClient(Config.get_api_url())


def search(
    query: str,
    limit: int = 10,
    offset: int = 0,
    with_if: bool = False,
) -> SearchResult:
    """
    Full-text search across works.

    Uses FTS5 index for fast searching across titles, abstracts, and authors.

    Args:
        query: Search query (supports FTS5 syntax)
        limit: Maximum results to return
        offset: Skip first N results (for pagination)
        with_if: Include impact factor data (OpenAlex)

    Returns:
        SearchResult with matching works

    Example:
        >>> from crossref_local import search
        >>> results = search("machine learning")
        >>> print(f"Found {results.total} matches")
    """
    if Config.get_mode() == "http":
        client = _get_http_client()
        return client.search(query=query, limit=limit, offset=offset, with_if=with_if)
    return fts.search(query, limit, offset)


def count(query: str) -> int:
    """
    Count matching works without fetching results.

    Args:
        query: FTS5 search query

    Returns:
        Number of matching works
    """
    if Config.get_mode() == "http":
        client = _get_http_client()
        result = client.search(query=query, limit=1)
        return result.total
    return fts.count(query)


def get(doi: str) -> Optional[Work]:
    """
    Get a work by DOI.

    Args:
        doi: Digital Object Identifier

    Returns:
        Work object or None if not found

    Example:
        >>> from crossref_local import get
        >>> work = get("10.1038/nature12373")
        >>> print(work.title)
    """
    if Config.get_mode() == "http":
        client = _get_http_client()
        return client.get(doi)
    db = get_db()
    metadata = db.get_metadata(doi)
    if metadata:
        return Work.from_metadata(doi, metadata)
    return None


def get_many(dois: List[str]) -> List[Work]:
    """
    Get multiple works by DOI.

    Args:
        dois: List of DOIs

    Returns:
        List of Work objects (missing DOIs are skipped)
    """
    if Config.get_mode() == "http":
        client = _get_http_client()
        return client.get_many(dois)
    db = get_db()
    works = []
    for doi in dois:
        metadata = db.get_metadata(doi)
        if metadata:
            works.append(Work.from_metadata(doi, metadata))
    return works


def exists(doi: str) -> bool:
    """
    Check if a DOI exists in the database.

    Args:
        doi: Digital Object Identifier

    Returns:
        True if DOI exists
    """
    if Config.get_mode() == "http":
        client = _get_http_client()
        return client.exists(doi)
    db = get_db()
    row = db.fetchone("SELECT 1 FROM works WHERE doi = ?", (doi,))
    return row is not None


def configure(db_path: str) -> None:
    """
    Configure for local database access.

    Args:
        db_path: Path to CrossRef SQLite database

    Example:
        >>> from crossref_local import configure
        >>> configure("/path/to/crossref.db")
    """
    Config.set_db_path(db_path)
    close_db()  # Reset singleton to use new path


def configure_http(api_url: str = "http://localhost:8333") -> None:
    """
    Configure for HTTP API access.

    Args:
        api_url: URL of CrossRef Local API server

    Example:
        >>> from crossref_local import configure_http
        >>> configure_http("http://localhost:8333")
        >>> # Or via SSH tunnel:
        >>> # ssh -L 8333:127.0.0.1:8333 your-server
        >>> configure_http()  # Uses default localhost:8333
    """
    Config.set_api_url(api_url)


# Backward compatibility alias
configure_remote = configure_http


def enrich(
    results: SearchResult,
    include_citations: bool = True,
    include_references: bool = True,
) -> SearchResult:
    """
    Enrich search results with full metadata (citations, references).

    The search() function returns basic metadata for speed. This function
    fetches full metadata for each work, adding citation counts and references.

    Args:
        results: SearchResult from search()
        include_citations: Include citation counts
        include_references: Include reference DOIs

    Returns:
        SearchResult with enriched works

    Example:
        >>> from crossref_local import search, enrich
        >>> results = search("machine learning", limit=10)
        >>> enriched = enrich(results)
        >>> for work in enriched:
        ...     print(f"{work.title}: {work.citation_count} citations")
    """
    enriched_works = []
    for work in results.works:
        full_work = get(work.doi)
        if full_work:
            enriched_works.append(full_work)
        else:
            # Keep original if full metadata not available
            enriched_works.append(work)

    return SearchResult(
        works=enriched_works,
        total=results.total,
        query=results.query,
        elapsed_ms=results.elapsed_ms,
    )


def enrich_dois(
    dois: List[str],
    include_citations: bool = True,
    include_references: bool = True,
) -> List[Work]:
    """
    Enrich a list of DOIs with full metadata.

    Fetches complete metadata for each DOI including citation counts
    and reference lists.

    Args:
        dois: List of DOIs to enrich
        include_citations: Include citation counts
        include_references: Include reference DOIs

    Returns:
        List of Work objects with full metadata

    Example:
        >>> from crossref_local import enrich_dois
        >>> works = enrich_dois(["10.1038/nature12373", "10.1126/science.aax0758"])
        >>> for w in works:
        ...     print(f"{w.doi}: {w.citation_count} citations, {len(w.references)} refs")
    """
    return get_many(dois)


def get_mode() -> str:
    """
    Get current mode.

    Returns:
        "db" or "http"
    """
    return Config.get_mode()


def info() -> dict:
    """
    Get database/API information.

    Fast by design: counts come from the ``db_stats`` cache (exact,
    written by :func:`refresh_stats`) or from ``MAX(rowid)`` estimates
    when the cache is absent — never from ``COUNT(*)`` full scans
    (~17.5 s on the production database). The ``counts_source`` field
    labels which path produced the numbers (``"exact"`` /
    ``"estimated"`` / ``"unavailable"``).

    Returns:
        Dictionary with database stats and mode info
    """
    mode = Config.get_mode()

    if mode == "http":
        client = _get_http_client()
        # Use /health (fast) instead of /info (slow COUNT(*) on large DBs)
        try:
            health = client.health(timeout=5)
        except (ConnectionError, OSError):
            return {
                "mode": "http",
                "status": "unreachable",
                "api_url": client.base_url,
                "error": f"Cannot connect to {client.base_url}",
            }
        result = {
            "mode": "http",
            "status": "ok" if health.get("status") == "healthy" else "degraded",
            "api_url": client.base_url,
            "db_path": health.get("database_path", "unknown"),
        }
        # Try /info with short timeout for counts
        old_timeout = client.timeout
        client.timeout = 5
        try:
            info_data = client._request("/info")
            if info_data:
                result["works"] = info_data.get("total_papers", 0)
                result["fts_indexed"] = info_data.get("fts_indexed", 0)
                result["citations"] = info_data.get("citations", 0)
                # Older servers do not send counts_source — label their
                # MAX(rowid)-style numbers honestly as estimates.
                result["counts_source"] = info_data.get(
                    "counts_source", "estimated"
                )
                result["counts_computed_at"] = info_data.get(
                    "counts_computed_at"
                )
        except Exception:
            result["works"] = 0
            result["fts_indexed"] = 0
            result["citations"] = 0
            result["counts_source"] = "unavailable"
            result["note"] = "/info timed out (server may need update)"
        finally:
            client.timeout = old_timeout
        return result

    db = get_db()

    # Cache-first counts (exact when db_stats is present, MAX(rowid)
    # estimates otherwise). NEVER COUNT(*) — see _core/stats.py.
    counts = stats.get_counts(db)

    return {
        "mode": "db",
        "status": "ok",
        "db_path": str(Config.get_db_path()),
        **counts,
    }
