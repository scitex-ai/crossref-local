"""FastAPI server for CrossRef Local.

This module re-exports from the modular server package for backwards
compatibility, so ``crossref_local._server.server:app`` keeps working as a
uvicorn target.

It used to read ``from .server import app`` — inside ``_server/server.py``
that names THIS module, so the import found a half-initialised copy of
itself and raised. It has to reach the package, one level up.

Usage:
    crossref-local api                    # Run on default port 31291
    crossref-local api --port 8080        # Custom port

    # Or directly:
    uvicorn crossref_local.server:app --host 0.0.0.0 --port 31291
"""

# Re-export from the modular server package (crossref_local._server).
from . import app, run_server, DEFAULT_PORT, DEFAULT_HOST

__all__ = ["app", "run_server", "DEFAULT_PORT", "DEFAULT_HOST"]

if __name__ == "__main__":
    run_server()
