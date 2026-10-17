"""Citation network endpoints."""

try:
    from fastapi import APIRouter, Query
except ImportError:  # fastapi absent — imported only under SERVER_AVAILABLE
    APIRouter = None  # type: ignore[assignment]
    Query = None  # type: ignore[assignment]

from .._core.citations import get_citing, get_cited, get_citation_count, CitationNetwork
from .models import (
    CitingResponse,
    CitedResponse,
    CitationCountResponse,
    CitationNetworkResponse,
)

router = APIRouter(prefix="/citations", tags=["citations"])


@router.get("/{doi:path}/citing", response_model=CitingResponse)
def get_citing_papers(
    doi: str,
    limit: int = Query(100, ge=1, le=1000, description="Max papers to return"),
):
    """
    Get papers that cite this DOI.

    Examples:
        /citations/10.1038/nature12373/citing
        /citations/10.1038/nature12373/citing?limit=50
    """
    citing_dois = get_citing(doi, limit=limit)
    return CitingResponse(
        doi=doi,
        citing_count=len(citing_dois),
        papers=citing_dois,
    )


@router.get("/{doi:path}/cited", response_model=CitedResponse)
def get_cited_papers(
    doi: str,
    limit: int = Query(100, ge=1, le=1000, description="Max papers to return"),
):
    """
    Get papers cited by this DOI (references).

    Examples:
        /citations/10.1038/nature12373/cited
        /citations/10.1038/nature12373/cited?limit=50
    """
    cited_dois = get_cited(doi, limit=limit)
    return CitedResponse(
        doi=doi,
        cited_count=len(cited_dois),
        papers=cited_dois,
    )


@router.get("/{doi:path}/count", response_model=CitationCountResponse)
def get_citation_count_endpoint(doi: str):
    """
    Get citation count for a DOI.

    Examples:
        /citations/10.1038/nature12373/count
    """
    count = get_citation_count(doi)
    return CitationCountResponse(doi=doi, citation_count=count)


@router.get("/{doi:path}/network", response_model=CitationNetworkResponse)
def get_citation_network(
    doi: str,
    depth: int = Query(1, ge=1, le=3, description="Network depth (1-3)"),
    max_citing: int = Query(25, ge=1, le=100, description="Max citing per node"),
    max_cited: int = Query(25, ge=1, le=100, description="Max cited per node"),
):
    """
    Get citation network graph for a DOI.

    Returns nodes (papers) and edges (citation relationships).

    Examples:
        /citations/10.1038/nature12373/network
        /citations/10.1038/nature12373/network?depth=2&max_citing=50
    """
    network = CitationNetwork(
        doi,
        depth=depth,
        max_citing=max_citing,
        max_cited=max_cited,
    )
    data = network.to_dict()
    return CitationNetworkResponse(
        center_doi=data["center_doi"],
        depth=data["depth"],
        total_nodes=data["stats"]["total_nodes"],
        total_edges=data["stats"]["total_edges"],
        nodes=data["nodes"],
        edges=data["edges"],
    )
