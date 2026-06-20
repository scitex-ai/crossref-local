"""Cache utility functions for crossref-local.

Provides path handling and validation utilities for the cache module.
"""

import os as _os
import re as _re
from pathlib import Path as _Path
from typing import Optional

__all__ = [
    "sanitize_name",
    "get_cache_dir",
    "cache_path",
    "meta_path",
]


# Valid cache name pattern: alphanumeric, underscores, hyphens only
_CACHE_NAME_PATTERN = _re.compile(r"^[a-zA-Z0-9_-]+$")


def sanitize_name(name: str) -> str:
    """Sanitize cache name to prevent path traversal.

    Args:
        name: Cache name to sanitize

    Returns:
        Sanitized name

    Raises:
        ValueError: If name contains invalid characters
    """
    if not name:
        raise ValueError("Cache name cannot be empty")
    if not _CACHE_NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid cache name '{name}': only alphanumeric, underscores, and hyphens allowed"
        )
    if len(name) > 64:
        raise ValueError(f"Cache name too long: {len(name)} chars (max 64)")
    return name


def get_cache_dir(user_id: Optional[str] = None) -> _Path:
    """Get cache directory, creating if needed.

    The default location is ``$SCITEX_DIR/crossref-local/runtime/cache/``
    (where ``$SCITEX_DIR`` defaults to ``~/.scitex``).  This may be
    overridden via ``CROSSREF_LOCAL_CACHE_DIR``.

    Args:
        user_id: Optional user ID for multi-tenant scoping.
                 If provided, creates a user-specific subdirectory.
    """
    env_dir = _os.environ.get("CROSSREF_LOCAL_CACHE_DIR")
    if env_dir:
        cache_dir = _Path(env_dir)
    else:
        from crossref_local._core.paths import state_dir as _state_dir

        cache_dir = _state_dir("cache")
    # Add user subdirectory for multi-tenant support
    if user_id:
        # Sanitize user_id as well
        safe_user_id = _re.sub(r"[^a-zA-Z0-9_-]", "", user_id[:16])
        if safe_user_id:
            cache_dir = cache_dir / safe_user_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def cache_path(name: str, user_id: Optional[str] = None) -> _Path:
    """Get path for a named cache.

    Args:
        name: Cache name (will be sanitized)
        user_id: Optional user ID for multi-tenant scoping

    Returns:
        Path to cache file
    """
    safe_name = sanitize_name(name)
    return get_cache_dir(user_id) / f"{safe_name}.json"


def meta_path(name: str, user_id: Optional[str] = None) -> _Path:
    """Get path for cache metadata.

    Args:
        name: Cache name (will be sanitized)
        user_id: Optional user ID for multi-tenant scoping

    Returns:
        Path to metadata file
    """
    safe_name = sanitize_name(name)
    return get_cache_dir(user_id) / f"{safe_name}.meta.json"
