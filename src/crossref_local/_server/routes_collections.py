"""Collection management endpoints with file download support."""

import tempfile
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException, Query, Request
    from fastapi.responses import FileResponse
except ImportError:  # fastapi absent — imported only under SERVER_AVAILABLE
    APIRouter = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    Query = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    FileResponse = None  # type: ignore[assignment]

from .. import cache
from .._cache.utils import sanitize_name
from .models import CollectionCreateRequest, CollectionInfo


# Allowed fields for field filtering (whitelist)
ALLOWED_FIELDS = {
    "doi",
    "title",
    "authors",
    "year",
    "journal",
    "volume",
    "issue",
    "page",
    "abstract",
    "citation_count",
    "references",
    "issn",
    "publisher",
}

# Maximum limits
MAX_LIMIT = 10000
MAX_DOIS = 1000

router = APIRouter(prefix="/collections", tags=["collections"])


def _get_user_id(request: Request) -> Optional[str]:
    """Get user ID from request state (set by middleware)."""
    return getattr(request.state, "user_id", None)


@router.get("")
def list_collections(request: Request):
    """
    List all collections.

    For cloud API (with X-User-ID header), returns only user's collections.
    For local API, returns all collections.
    """
    user_id = _get_user_id(request)
    caches = cache.list_caches(user_id=user_id)
    return {
        "count": len(caches),
        "collections": [c.to_dict() for c in caches],
    }


@router.post("", response_model=CollectionInfo)
def create_collection(request: Request, body: CollectionCreateRequest):
    """
    Create a new collection from search query or DOI list.

    Request body:
        {"name": "epilepsy", "query": "epilepsy seizure", "limit": 500}
        or
        {"name": "my_papers", "dois": ["10.1038/...", "10.1016/..."]}
    """
    user_id = _get_user_id(request)

    # Validate collection name
    try:
        sanitize_name(body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not body.query and not body.dois:
        raise HTTPException(
            status_code=400,
            detail="Must provide 'query' or 'dois'",
        )

    # Validate limits
    if body.limit > MAX_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Limit exceeds maximum ({MAX_LIMIT})",
        )

    if body.dois and len(body.dois) > MAX_DOIS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many DOIs ({len(body.dois)}). Maximum: {MAX_DOIS}",
        )

    try:
        info = cache.create(
            body.name,
            query=body.query,
            dois=body.dois,
            limit=body.limit,
            user_id=user_id,
        )
        return CollectionInfo(**info.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}")
def query_collection(
    name: str,
    request: Request,
    fields: Optional[str] = Query(None, description="Comma-separated field list"),
    include_abstract: bool = Query(False, description="Include abstracts"),
    include_references: bool = Query(False, description="Include references"),
    include_citations: bool = Query(False, description="Include citation counts"),
    year_min: Optional[int] = Query(None, description="Filter by min year"),
    year_max: Optional[int] = Query(None, description="Filter by max year"),
    journal: Optional[str] = Query(None, description="Filter by journal"),
    limit: Optional[int] = Query(None, description="Max results"),
):
    """
    Query a collection with field filtering.

    Returns minimal data to reduce response size.
    Use 'fields' parameter to specify exactly which fields to return.

    Examples:
        /collections/epilepsy?fields=doi,title,year
        /collections/epilepsy?year_min=2020&include_citations=true
    """
    user_id = _get_user_id(request)

    # Validate collection name
    try:
        sanitize_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not cache.exists(name, user_id=user_id):
        raise HTTPException(status_code=404, detail=f"Collection not found: {name}")

    # Validate and filter fields
    field_list = None
    if fields:
        field_list = [f.strip() for f in fields.split(",")]
        invalid_fields = set(field_list) - ALLOWED_FIELDS
        if invalid_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid fields: {invalid_fields}. Allowed: {ALLOWED_FIELDS}",
            )

    papers = cache.query(
        name,
        fields=field_list,
        include_abstract=include_abstract,
        include_references=include_references,
        include_citations=include_citations,
        year_min=year_min,
        year_max=year_max,
        journal=journal,
        limit=limit,
        user_id=user_id,
    )

    return {
        "name": name,
        "count": len(papers),
        "papers": papers,
    }


@router.get("/{name}/stats")
def collection_stats(name: str, request: Request):
    """
    Get collection statistics.

    Returns year distribution, top journals, citation stats.
    """
    user_id = _get_user_id(request)

    try:
        sanitize_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not cache.exists(name, user_id=user_id):
        raise HTTPException(status_code=404, detail=f"Collection not found: {name}")

    stats = cache.stats(name, user_id=user_id)
    return {"name": name, **stats}


@router.get("/{name}/download")
def download_collection(
    name: str,
    request: Request,
    format: str = Query("json", description="Export format: json, csv, bibtex, dois"),
    fields: Optional[str] = Query(None, description="Fields to include (json/csv)"),
):
    """
    Download collection as a file.

    Supports multiple formats:
    - json: Full JSON with all fields or specified fields
    - csv: CSV format with specified fields
    - bibtex: BibTeX format for bibliography
    - dois: Plain text list of DOIs

    Examples:
        /collections/epilepsy/download?format=json
        /collections/epilepsy/download?format=bibtex
        /collections/epilepsy/download?format=csv&fields=doi,title,year
    """
    user_id = _get_user_id(request)

    try:
        sanitize_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not cache.exists(name, user_id=user_id):
        raise HTTPException(status_code=404, detail=f"Collection not found: {name}")

    # Determine file extension and media type
    format_info = {
        "json": ("application/json", ".json"),
        "csv": ("text/csv", ".csv"),
        "bibtex": ("application/x-bibtex", ".bib"),
        "dois": ("text/plain", ".txt"),
    }

    if format not in format_info:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Use: json, csv, bibtex, dois",
        )

    media_type, ext = format_info[format]
    filename = f"{name}{ext}"

    # Export to temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False) as tmp:
        field_list = fields.split(",") if fields else None
        cache.export(
            name,
            tmp.name,
            format=format,
            fields=field_list,
            user_id=user_id,
        )
        tmp_path = tmp.name

    return FileResponse(
        tmp_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{name}")
def delete_collection(name: str, request: Request):
    """
    Delete a collection.
    """
    user_id = _get_user_id(request)

    try:
        sanitize_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not cache.exists(name, user_id=user_id):
        raise HTTPException(status_code=404, detail=f"Collection not found: {name}")

    deleted = cache.delete(name, user_id=user_id)

    return {"deleted": deleted, "name": name}
