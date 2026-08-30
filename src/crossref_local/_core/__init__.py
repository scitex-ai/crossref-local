#!/usr/bin/env python3
"""Internal core modules for crossref_local."""

from .api import (
    close_stores,
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
from .export import SUPPORTED_FORMATS, save
from .models import SearchResult, Work
from .store import (
    CITATIONS,
    CORPUS_STATS,
    JOURNALS,
    SYNC_STATE,
    WORKS,
    citations_store,
    corpus_stats_store,
    journals_store,
    sync_state_store,
    works_store,
)
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
    # Store — the schemas and the openers that hand out a bare Store.
    # There is no connection wrapper here on purpose: callers use the
    # primitive's own get/rows/put.
    "WORKS",
    "CITATIONS",
    "JOURNALS",
    "CORPUS_STATS",
    "SYNC_STATE",
    "works_store",
    "citations_store",
    "journals_store",
    "corpus_stats_store",
    "sync_state_store",
    "close_stores",
    # Config
    "Config",
    # Export
    "save",
    "SUPPORTED_FORMATS",
    # Update (incremental refresh)
    "update",
]

# EOF
