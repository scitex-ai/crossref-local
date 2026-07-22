"""Pydantic models for API responses."""

from typing import Optional, List
from pydantic import BaseModel

from .. import __version__


class WorkResponse(BaseModel):
    """Work metadata response."""

    doi: str
    title: Optional[str] = None
    authors: List[str] = []
    year: Optional[int] = None
    journal: Optional[str] = None
    issn: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    page: Optional[str] = None
    abstract: Optional[str] = None
    citation_count: Optional[int] = None
    impact_factor: Optional[float] = None
    impact_factor_source: Optional[str] = None


class LimitInfoResponse(BaseModel):
    """Information about result limiting."""

    requested: int
    returned: int
    total_available: int
    capped: bool = False
    capped_reason: Optional[str] = None
    stage: str = "crossref-local"


class SearchResponse(BaseModel):
    """Search results response."""

    query: str
    total: int
    returned: int
    elapsed_ms: float
    results: List[WorkResponse]
    limit_info: Optional[LimitInfoResponse] = None


class InfoResponse(BaseModel):
    """Database info response.

    ``counts_source`` labels how the counts were produced: ``"exact"``
    (from the ``db_stats`` cache) or ``"estimated"`` (``MAX(rowid)``).
    """

    name: str = "CrossRef Local API"
    version: str = __version__
    status: str = "running"
    mode: str = "local"
    total_papers: int
    fts_indexed: int
    citations: Optional[int] = 0
    counts_source: str = "estimated"
    counts_computed_at: Optional[str] = None
    database_path: str


class BatchRequest(BaseModel):
    """Batch DOI lookup request."""

    dois: List[str]


class BatchResponse(BaseModel):
    """Batch DOI lookup response."""

    requested: int
    found: int
    results: List[WorkResponse]


# Citation models
class CitingResponse(BaseModel):
    """Papers citing a DOI."""

    doi: str
    citing_count: int
    papers: List[str]


class CitedResponse(BaseModel):
    """Papers cited by a DOI."""

    doi: str
    cited_count: int
    papers: List[str]


class CitationCountResponse(BaseModel):
    """Citation count for a DOI."""

    doi: str
    citation_count: int


class CitationNetworkResponse(BaseModel):
    """Citation network graph."""

    center_doi: str
    depth: int
    total_nodes: int
    total_edges: int
    nodes: List[dict]
    edges: List[dict]


# Collection models
class CollectionCreateRequest(BaseModel):
    """Create collection request."""

    name: str
    query: Optional[str] = None
    dois: Optional[List[str]] = None
    limit: int = 1000


class CollectionInfo(BaseModel):
    """Collection information."""

    name: str
    path: str
    size_bytes: int
    size_mb: float
    paper_count: int
    created_at: str
    query: Optional[str] = None


class CollectionQueryRequest(BaseModel):
    """Query collection request."""

    fields: Optional[List[str]] = None
    include_abstract: bool = False
    include_references: bool = False
    include_citations: bool = False
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    journal: Optional[str] = None
    limit: Optional[int] = None
