"""FastAPI server for CrossRef Local with FTS5 search.

Modular server structure:
- routes_works.py: /works endpoints
- routes_citations.py: /citations endpoints
- routes_collections.py: /collections endpoints
- routes_compat.py: Legacy /api/* endpoints
- models.py: Pydantic response models
- middleware.py: Request middleware
"""

import os

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:  # fastapi absent — the [server]-gated HTTP capability only
    FastAPI = None  # type: ignore[assignment]
    CORSMiddleware = None  # type: ignore[assignment]

SERVER_AVAILABLE = FastAPI is not None
SERVER_EXTRA_HINT = "pip install 'crossref-local[all]'"

from .. import __version__

if SERVER_AVAILABLE:
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
else:
    app = None


def _register_routes() -> None:
    """Register plain route functions against the FastAPI app.

    A no-op without fastapi: there is no app to register against.
    """
    if app is None:
        return
    app.get("/")(root)
    app.get("/health")(health)
    app.get("/info")(info)


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


def health():
    """Health check endpoint."""
    from .._core.db import get_db

    db = get_db()
    return {
        "status": "healthy",
        "database_connected": db is not None,
        "database_path": str(db.db_path) if db else None,
    }


def info():
    """Get database statistics."""
    from .._core.db import get_db
    from .models import InfoResponse

    db = get_db()

    # Use MAX(rowid) as fast O(1) approximation (COUNT(*) is too slow on 167M+ rows)
    row = db.fetchone("SELECT MAX(rowid) as count FROM works")
    work_count = row["count"] if row else 0

    try:
        row = db.fetchone("SELECT MAX(rowid) as count FROM works_fts")
        fts_count = row["count"] if row else 0
    except Exception:
        fts_count = 0

    try:
        row = db.fetchone("SELECT MAX(rowid) as count FROM citations")
        citation_count = row["count"] if row else 0
    except Exception:
        citation_count = 0

    return InfoResponse(
        total_papers=work_count,
        fts_indexed=fts_count,
        citations=citation_count,
        database_path=str(db.db_path),
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


_register_routes()


def run_server(host: str = None, port: int = None, force: bool = False):
    """Run the FastAPI server.

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to listen on (default: 31291)
        force: If True, kill any existing process using the port
    """
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError(
            "uvicorn is not installed, so the crossref-local HTTP server is "
            f"unavailable. Install it with: {SERVER_EXTRA_HINT}"
        ) from e

    if app is None:
        raise RuntimeError(
            "fastapi is not installed, so the crossref-local HTTP server is "
            f"unavailable. Install it with: {SERVER_EXTRA_HINT}"
        )

    host = host or DEFAULT_HOST
    port = port or DEFAULT_PORT

    if force:
        from .._cli.utils import kill_process_on_port

        kill_process_on_port(port)

    uvicorn.run(app, host=host, port=port)


__all__ = ["app", "run_server", "DEFAULT_PORT", "DEFAULT_HOST"]
