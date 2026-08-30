"""FastAPI server for CrossRef Local.

Modular server structure:
- routes_works.py: /works endpoints
- routes_citations.py: /citations endpoints
- routes_collections.py: /collections endpoints
- routes_compat.py: Legacy /api/* endpoints
- models.py: Pydantic response models
- middleware.py: Request middleware
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from .middleware import UserContextMiddleware
from .routes_works import router as works_router
from .routes_citations import router as citations_router
from .routes_collections import router as collections_router
from .routes_compat import router as compat_router

# Create FastAPI app
app = FastAPI(
    title="CrossRef Local API",
    description="Fast full-text search across 167M+ scholarly works",
    version=__version__,
)

# Middleware
app.add_middleware(UserContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(works_router)
app.include_router(citations_router)
app.include_router(collections_router)
app.include_router(compat_router)


@app.get("/")
def root():
    """API root with endpoint information."""
    return {
        "name": "CrossRef Local API",
        "version": __version__,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "info": "/info",
            "search": "/works?q=<query>",
            "get_by_doi": "/works/{doi}",
            "batch": "/works/batch",
            "citations_citing": "/citations/{doi}/citing",
            "citations_cited": "/citations/{doi}/cited",
            "citations_count": "/citations/{doi}/count",
            "citations_network": "/citations/{doi}/network",
            "collections_list": "/collections",
            "collections_create": "/collections (POST)",
            "collections_get": "/collections/{name}",
            "collections_stats": "/collections/{name}/stats",
            "collections_download": "/collections/{name}/download",
            "collections_delete": "/collections/{name} (DELETE)",
        },
    }


@app.get("/health")
def health():
    """Health check endpoint.

    Reports the store this host reads under ``store``. That value is a
    credential-free description, never the connection string: a DSN can
    carry a password and this response is public.

    ``store_available`` only resolves the target — it opens no connection
    — so a probe of this endpoint stays O(1) no matter how far away the
    store is. A target that resolves but refuses the connection surfaces
    at first real use, naming the address and the reason.
    """
    from .._core.config import Config, store_available

    available = store_available()
    return {
        "status": "healthy" if available else "degraded",
        "store": Config.describe_store(),
    }


@app.get("/info")
def info():
    """Get corpus statistics.

    Counts come from the exact-count cache written by ``refresh_stats``
    (``crossref-local sync-stats``), or are reported as unavailable when
    that cache is absent. This endpoint NEVER counts: the store has no
    aggregate, so counting means reading every record, and a probe must
    not cost that. ``counts_source`` labels which path produced the
    numbers.
    """
    from .._core.config import Config
    from .._core.stats import get_counts
    from .models import InfoResponse

    counts = get_counts()

    return InfoResponse(
        total_papers=counts["works"],
        fts_indexed=counts["fts_indexed"],
        citations=counts["citations"],
        counts_source=counts["counts_source"],
        counts_computed_at=counts["counts_computed_at"],
        store=Config.describe_store(),
    )


# Default port: SCITEX convention (3129X scheme)
DEFAULT_PORT = int(
    os.environ.get(
        "SCITEX_SCHOLAR_CROSSREF_PORT",
        os.environ.get("CROSSREF_LOCAL_PORT", "31291"),
    )
)
DEFAULT_HOST = os.environ.get(
    "SCITEX_SCHOLAR_CROSSREF_HOST",
    os.environ.get("CROSSREF_LOCAL_HOST", "0.0.0.0"),
)


def run_server(host: str = None, port: int = None, force: bool = False):
    """Run the FastAPI server.

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to listen on (default: 31291)
        force: If True, kill any existing process using the port
    """
    import uvicorn

    host = host or DEFAULT_HOST
    port = port or DEFAULT_PORT

    if force:
        from .._cli.utils import kill_process_on_port

        kill_process_on_port(port)

    uvicorn.run(app, host=host, port=port)


__all__ = ["app", "run_server", "DEFAULT_PORT", "DEFAULT_HOST"]
