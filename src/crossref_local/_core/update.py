#!/usr/bin/env python3
"""Incremental store update for crossref_local.

Thin wrapper around :mod:`crossref_local._core.ingest`, so the CLI
(``crossref-local update-db``) and the Python API (``crossref_local.update``)
share one code path.

The engine used to live under ``scripts/`` and be loaded by file path — this
module resolved that path, checked it existed, and executed the file through
``importlib``. None of that is needed now that the engine is an ordinary
module: an import error names the module and the line, where a missing-file
error named only a path and left the reader to guess which copy was meant.
"""

from typing import Optional as _Optional

from .ingest import differential_update as _differential_update

__all__ = ["update"]


def update(
    since: _Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Incrementally update the local CrossRef store.

    Fetches only the works newer than the recorded watermark (or ``since``
    when given) from the CrossRef REST API and upserts them.

    Parameters
    ----------
    since : str, optional
        Override start date (``YYYY-MM-DD``). Defaults to the recorded
        ``last_sync_date``.
    dry_run : bool
        Preview only — count what would be upserted without writing.

    Returns
    -------
    dict
        Statistics from the ingest run: ``records_upserted``,
        ``elapsed_seconds``, ``last_sync_date`` (and ``dry_run`` when
        applicable).
    """
    return _differential_update(since=since, dry_run=dry_run)

# EOF
