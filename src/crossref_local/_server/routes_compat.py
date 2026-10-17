"""Backwards-compatible legacy API endpoints."""

from typing import Optional

try:
    from fastapi import APIRouter, HTTPException
except ImportError:  # fastapi absent — imported only under SERVER_AVAILABLE
    APIRouter = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]

from .._core import fts
from .._core.db import get_db
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


@router.get("/stats/")
def api_stats_compat():
    """Backwards-compatible stats endpoint."""
    db = get_db()

    row = db.fetchone("SELECT MAX(rowid) as count FROM works")
    work_count = row["count"] if row else 0

    # Get table names
    tables = []
    for row in db.fetchall("SELECT name FROM sqlite_master WHERE type='table'"):
        tables.append(row["name"])

    # Get index names
    indices = []
    for row in db.fetchall("SELECT name FROM sqlite_master WHERE type='index'"):
        if row["name"]:
            indices.append(row["name"])

    return {
        "total_papers": work_count,
        "database_size_mb": None,
        "year_range": None,
        "total_journals": 0,
        "total_citations": None,
        "tables": tables,
        "indices": indices,
    }
