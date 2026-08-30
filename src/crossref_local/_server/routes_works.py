"""Work search and retrieval endpoints."""

import time
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from .._core import fts
from .._core.models import Work
from .._core.store import works_store
from .._impact_factor import impact_factor_for_issn
from .models import (
    BatchRequest,
    BatchResponse,
    SearchResponse,
    WorkResponse,
)

router = APIRouter(tags=["works"])


def _metadata_of(row) -> Optional[dict]:
    """The parsed ``metadata`` of a work row, or None for a miss.

    ``metadata`` is a declared JSON field, so the primitive hands back a
    ``dict``; nothing is decompressed or re-parsed here.
    """
    if row is None:
        return None
    return row.values.get("metadata") or None


def _get_impact_factor(issn: str) -> Optional[float]:
    """The journal's OpenAlex IF proxy for one ISSN.

    The per-ISSN cache this module used to keep lives in
    :mod:`crossref_local._impact_factor.journal_lookup` now, as a single
    ISSN -> proxy index: the store has no filtered read, so one lookup per
    ISSN would be one full scan per ISSN.
    """
    return impact_factor_for_issn(issn)


@router.get("/works", response_model=SearchResponse)
def search_works(
    q: str = Query(..., description='Search query (AND / OR / NOT / "phrases")'),
    limit: int = Query(10, ge=1, description="Max results"),
    offset: int = Query(0, ge=0, description="Skip first N results"),
    with_if: bool = Query(False, description="Include impact factor (OpenAlex)"),
):
    """
    Full-text search across works.

    Searches titles, abstracts, authors and container titles. Supports
    AND, OR, NOT and "exact phrases".

    Examples:
        /works?q=machine learning
        /works?q="neural network" AND hippocampus
        /works?q=CRISPR&limit=20&with_if=true
    """
    start = time.perf_counter()

    try:
        results = fts.search(q, limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Search error: {e}")

    work_responses = []
    for w in results.works:
        if_val = _get_impact_factor(w.issn) if with_if and w.issn else None
        work_responses.append(
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
                impact_factor=if_val,
                impact_factor_source="OpenAlex" if if_val else None,
            )
        )

    elapsed_ms = (time.perf_counter() - start) * 1000

    # Build limit_info from search result
    limit_info = None
    if results.limit_info:
        from .models import LimitInfoResponse

        limit_info = LimitInfoResponse(
            requested=results.limit_info.requested,
            returned=results.limit_info.returned,
            total_available=results.limit_info.total_available,
            capped=results.limit_info.capped,
            capped_reason=results.limit_info.capped_reason,
            stage=results.limit_info.stage,
        )

    return SearchResponse(
        query=q,
        total=results.total,
        returned=len(results.works),
        elapsed_ms=round(elapsed_ms, 2),
        results=work_responses,
        limit_info=limit_info,
    )


@router.get("/works/{doi:path}", response_model=Optional[WorkResponse])
def get_work(doi: str):
    """
    Get work metadata by DOI.

    Examples:
        /works/10.1038/nature12373
        /works/10.1016/j.cell.2020.01.001
    """
    metadata = _metadata_of(works_store().get({"doi": doi}))

    if metadata is None:
        raise HTTPException(status_code=404, detail=f"DOI not found: {doi}")

    work = Work.from_metadata(doi, metadata)

    return WorkResponse(
        doi=work.doi,
        title=work.title,
        authors=work.authors,
        year=work.year,
        journal=work.journal,
        issn=work.issn,
        volume=work.volume,
        issue=work.issue,
        page=work.page,
        abstract=work.abstract,
        citation_count=work.citation_count,
    )


@router.post("/works/batch", response_model=BatchResponse)
def get_works_batch(request: BatchRequest):
    """
    Get multiple works by DOI.

    Request body: {"dois": ["10.1038/...", "10.1016/..."]}
    """
    store = works_store()
    results = []

    for doi in request.dois:
        metadata = _metadata_of(store.get({"doi": doi}))
        if metadata:
            work = Work.from_metadata(doi, metadata)
            results.append(
                WorkResponse(
                    doi=work.doi,
                    title=work.title,
                    authors=work.authors,
                    year=work.year,
                    journal=work.journal,
                    abstract=work.abstract,
                    citation_count=work.citation_count,
                )
            )

    return BatchResponse(
        requested=len(request.dois),
        found=len(results),
        results=results,
    )
