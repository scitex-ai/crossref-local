"""Configuration for crossref_local.

The corpus lives in the fleet's shared store, so there is no database path
to resolve here and no environment variable that names one. DSN resolution
belongs to :func:`scitex_dev.store.host_store` and happens in
:mod:`crossref_local._core.store`; nothing in this package builds a DSN,
reads ``SCITEX_STORE_DSN`` directly, or keeps a second copy of that answer.

Two access modes remain, unchanged in meaning:

``db``
    Read the store on this host directly.
``http``
    Talk to a relay server over HTTP (``crossref-local relay``), for a
    machine that has no store of its own.
"""

import os as _os
from typing import Optional

__all__ = [
    "Config",
    "DEFAULT_PORT",
    "DEFAULT_API_URL",
    "store_available",
]

# Default port: SCITEX convention (3129X scheme)
# 31290: scitex-cloud, 31291: crossref-local, 31292: openalex-local, 31293: audio relay
DEFAULT_PORT = 31291

# Default remote API URLs (checked in order)
DEFAULT_API_URLS = [
    f"http://localhost:{DEFAULT_PORT}",  # SCITEX default
]
DEFAULT_API_URL = DEFAULT_API_URLS[0]


def store_available() -> bool:
    """Whether this host can resolve a store target at all.

    Resolution only — this does NOT open a connection. A reachability
    probe here would make every ``get_mode()`` call pay for a round trip,
    and mode selection is asked on almost every entry point. A target that
    resolves but refuses the connection surfaces as the store's own error
    at first use, which names the address and the reason; guessing at it
    from a boolean here would not.
    """
    from .store import target_for

    try:
        target_for("works")
    except Exception:
        return False
    return True


class Config:
    """Configuration container."""

    _api_url: Optional[str] = None
    _mode: str = "auto"  # "auto", "db", or "http"

    @classmethod
    def get_mode(cls) -> str:
        """
        Get current mode.

        Returns:
            "db" if reading the shared store directly
            "http" if using the HTTP API
        """
        if cls._mode == "auto":
            # Check environment variables (SCITEX takes priority)
            env_mode = _os.environ.get(
                "SCITEX_SCHOLAR_CROSSREF_MODE",
                _os.environ.get("CROSSREF_LOCAL_MODE", ""),
            ).lower()
            if env_mode in ("http", "remote", "api"):
                return "http"
            if env_mode in ("db", "local", "store"):
                return "db"

            # Check if API URL is set
            if cls._api_url or _os.environ.get("CROSSREF_LOCAL_API_URL"):
                return "http"

            return "db" if store_available() else "http"

        return cls._mode

    @classmethod
    def set_mode(cls, mode: str) -> None:
        """Set mode explicitly: 'db', 'http', or 'auto'."""
        if mode not in ("auto", "db", "http"):
            raise ValueError(f"Invalid mode: {mode}. Use 'auto', 'db', or 'http'")
        cls._mode = mode

    @classmethod
    def get_api_url(cls, auto_detect: bool = True) -> str:
        """
        Get API URL for remote mode.

        Args:
            auto_detect: If True, test each URL and use first working one

        Returns:
            API URL string
        """
        if cls._api_url:
            return cls._api_url

        env_url = _os.environ.get("CROSSREF_LOCAL_API_URL")
        if env_url:
            return env_url

        if auto_detect:
            working_url = cls._find_working_api()
            if working_url:
                cls._api_url = working_url
                return working_url

        return DEFAULT_API_URL

    @classmethod
    def _find_working_api(cls) -> Optional[str]:
        """Try each default API URL and return first working one."""
        import urllib.error
        import urllib.request

        for url in DEFAULT_API_URLS:
            try:
                req = urllib.request.Request(f"{url}/health", method="GET")
                req.add_header("Accept", "application/json")
                with urllib.request.urlopen(req, timeout=3) as response:
                    if response.status == 200:
                        return url
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                continue
        return None

    @classmethod
    def set_api_url(cls, url: str) -> None:
        """Set API URL for http mode."""
        cls._api_url = url.rstrip("/")
        cls._mode = "http"

    @classmethod
    def describe_store(cls) -> str:
        """A human-readable name for the store this host would read.

        Used by ``info()`` and ``/health`` in place of the database path
        those responses used to carry. Never the DSN: a DSN can hold a
        password, and these values are printed to terminals and returned
        over HTTP to clients.
        """
        from .store import PKG, target_for

        try:
            target = target_for("works")
        except Exception as exc:
            return f"unresolved ({type(exc).__name__})"
        describe = getattr(target, "describe", None)
        return describe() if callable(describe) else f"{PKG}/works"

    @classmethod
    def reset(cls) -> None:
        """Reset configuration (for testing)."""
        cls._api_url = None
        cls._mode = "auto"

# EOF
