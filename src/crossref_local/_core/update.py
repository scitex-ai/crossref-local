#!/usr/bin/env python3
"""Incremental database update for crossref_local.

Thin wrapper around the project's differential-update logic
(``scripts/database/10_differential_update.py``). Incrementally refreshes
the local ``works`` table from the CrossRef REST API — only works whose
``from-index-date`` is newer than the recorded ``_metadata.last_sync_date``
are fetched and upserted (INSERT OR REPLACE) with WAL safety.

The heavy lifting is NOT reimplemented here — this module only resolves
paths and forwards to ``differential_update`` so the CLI
(``crossref-local update``) and Python API (``crossref_local.update``)
share one code path. Mirrors openalex-local's ``_core/update.py``.
"""

import importlib.util as _importlib_util
import os as _os
from pathlib import Path as _Path
from typing import Optional as _Optional

from .config import get_db_path as _get_db_path

__all__ = ["update"]

# Repo root: <repo>/src/crossref_local/_core/update.py -> parents[3].
_REPO_ROOT = _Path(__file__).resolve().parents[3]
_DEFAULT_DIFFERENTIAL_UPDATE_SCRIPT = (
    _REPO_ROOT / "scripts" / "database" / "10_differential_update.py"
)
# Env override — lets callers (and tests) point at an alternate script
# that exposes the same ``differential_update`` entry point.
_SCRIPT_ENV_VAR = "CROSSREF_LOCAL_DIFFERENTIAL_UPDATE_SCRIPT"


def _differential_update_script() -> _Path:
    """Resolve the differential-update script path (env override first)."""
    env_path = _os.environ.get(_SCRIPT_ENV_VAR)
    if env_path:
        return _Path(env_path)
    return _DEFAULT_DIFFERENTIAL_UPDATE_SCRIPT


def _load_differential_update():
    """Load ``differential_update`` from the database script.

    The sync logic lives under ``scripts/`` (outside the importable
    package), so it is loaded by file path rather than reimplemented.
    """
    script = _differential_update_script()
    if not script.exists():
        raise FileNotFoundError(
            f"Differential update script not found: {script}"
        )
    spec = _importlib_util.spec_from_file_location(
        "_crossref_local_differential_update", script
    )
    module = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.differential_update


def _resolve_db_path(db_path: _Optional[str]) -> _Path:
    """Resolve the database path (explicit override or auto-discovery)."""
    if db_path:
        return _Path(db_path)
    try:
        return _get_db_path()
    except FileNotFoundError:
        # No DB yet — fall back to the repo-default location so a first
        # run can create it (mirrors the rebuild scripts' default path).
        return _REPO_ROOT / "data" / "crossref.db"


def update(
    db_path: _Optional[str] = None,
    since: _Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Incrementally update the local CrossRef database.

    Fetches only the works newer than the recorded ``last_sync_date``
    (or ``since`` when given) from the CrossRef REST API and upserts
    them into the database.

    Parameters
    ----------
    db_path : str, optional
        Database path override. Defaults to the package's normal
        discovery (``CROSSREF_LOCAL_DB`` env var, then default paths).
    since : str, optional
        Override start date (``YYYY-MM-DD``). Defaults to the DB's
        recorded ``_metadata.last_sync_date``.
    dry_run : bool
        Preview only — count what would be upserted without writing.

    Returns
    -------
    dict
        Statistics from ``differential_update``: ``records_upserted``,
        ``elapsed_seconds``, ``last_sync_date`` (and ``dry_run`` when
        applicable).
    """
    resolved_db = _resolve_db_path(db_path)

    differential_update = _load_differential_update()
    return differential_update(
        db_path=resolved_db,
        since=since,
        dry_run=dry_run,
    )

# EOF
