#!/usr/bin/env python3
"""Internal core modules for crossref_local."""

from .api import (
    configure,
    configure_http,
    configure_remote,
    count,
    enrich,
    enrich_dois,
    exists,
    get,
    get_many,
    get_mode,
    info,
    refresh_stats,
    search,
)
from .citations import (
    CitationNetwork,
    get_citation_count,
    get_cited,
    get_citing,
)
from .config import Config
from .db import Database, close_db, get_db
from .export import SUPPORTED_FORMATS, save
from .models import SearchResult, Work
from .update import update

__all__ = [
    # API functions
    "search",
    "count",
    "get",
    "get_many",
    "exists",
    "enrich",
    "enrich_dois",
    "configure",
    "configure_http",
    "configure_remote",
    "get_mode",
    "info",
    "refresh_stats",
    # Models
    "Work",
    "SearchResult",
    # Citations
    "get_citing",
    "get_cited",
    "get_citation_count",
    "CitationNetwork",
    # Database
    "Database",
    "get_db",
    "close_db",
    # Config
    "Config",
    # Export
    "save",
    "SUPPORTED_FORMATS",
    # Update (incremental refresh)
    "update",
]

# EOF
