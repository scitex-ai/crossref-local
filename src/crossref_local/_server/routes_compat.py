"""Backwards-compatible legacy API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException

from .._core import fts
from .._core.stats import get_counts
from .._core.store import (
    CITATIONS,
    CORPUS_STATS,
    JOURNALS,
    SYNC_STATE,
    WORKS,
)
from .models import WorkResponse
from .routes_works import get_work

router = APIRouter(prefix="/api", tags=["legacy"])


@router.get("/search/")
def api_search_compat(
    title: Optional[str] = None,
    q: Optional[str] = None,
    doi: Optional[str] = None,
    limit: int = 10,
):
    """Backwards-compatible search endpoint."""
    query = title or q

    if doi:
        # DOI lookup
        try:
            work = get_work(doi)
            return {
                "query": {"doi": doi},
                "results": [work.model_dump()],
                "total": 1,
                "returned": 1,
            }
        except HTTPException:
            return {"query": {"doi": doi}, "results": [], "total": 0, "returned": 0}

    if not query:
        raise HTTPException(
            status_code=400, detail="Specify q, title, or doi parameter"
        )

    # Call fts.search directly (not the endpoint function)
    results = fts.search(query, limit=limit, offset=0)
    return {
        "query": {
            "title": query,
            "doi": None,
            "year": None,
            "authors": None,
            "limit": limit,
        },
        "results": [
            WorkResponse(
                doi=w.doi,
                title=w.title,
                authors=w.authors,
                year=w.year,
                journal=w.journal,
                issn=w.issn,
                volume=w.volume,
                issue=w.issue,
                page=w.page,
                abstract=w.abstract,
                citation_count=w.citation_count,
            ).model_dump()
            for w in results.works
        ],
        "total": results.total,
        "returned": len(results.works),
    }


#: The collections this package declares. ``tables`` used to be read back
#: from the engine's own catalog, which answered with whatever physically
#: existed. The store primitive exposes no catalog, so this is the
#: declaration instead of an observation: it says what this package
#: defines, not what the server happens to hold.
_COLLECTION_NAMES = [
    schema.name for schema in (WORKS, CITATIONS, JOURNALS, CORPUS_STATS, SYNC_STATE)
]


@router.get("/stats/")
def api_stats_compat():
    """Backwards-compatible stats endpoint.

    Two fields changed meaning and cannot be restored:

    * ``tables`` is now the list of collections this package DECLARES,
      not a catalog read. Nothing can enumerate what a store physically
      holds.
    * ``indices`` is always empty. Indexing is a per-field policy on a
      schema, not a named object with a listable name, so there is no
      honest value to put here. The key is kept so existing clients do
      not fail on its absence.

    Counts come from the exact-count cache and are ``None`` when that
    cache has not been written — never a scan, and never a zero standing
    in for a number nobody measured. ``counts_source`` says which.
    """
    counts = get_counts()
    exact = counts.get("counts_source") == "exact"

    return {
        "total_papers": counts["works"] if exact else None,
        "database_size_mb": None,
        "year_range": None,
        "total_journals": 0,
        "total_citations": counts["citations"] if exact else None,
        "counts_source": counts.get("counts_source"),
        "counts_computed_at": counts.get("counts_computed_at"),
        "tables": list(_COLLECTION_NAMES),
        "indices": [],
    }
