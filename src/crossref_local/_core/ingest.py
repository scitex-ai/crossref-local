#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Differential (incremental) ingest of CrossRef works into the store.

Refreshes the works collection from the CrossRef REST API instead of the
~1.5 TB Public Data File dump: only works whose ``from-index-date`` is newer
than the recorded watermark are fetched and upserted.

Steps:
    1. Read the watermark from the sync-state collection.
    2. Deep-page the CrossRef REST API from ``from-index-date=<since>``
       (``cursor=*`` -> ``message.next-cursor`` until a short page arrives).
    3. Normalise each CrossRef JSON work into a works record and upsert it.
    4. Advance the watermark ONLY after a successful run, so an interrupted
       run re-covers the same range and leaves no gap.

WHY THIS LIVES IN THE PACKAGE NOW
---------------------------------
It used to be ``scripts/database/10_differential_update.py``, loaded by file
path through ``importlib.spec_from_file_location`` because it sat outside
the importable package — and it reached further still, prepending a
vendored loader project under ``vendor/`` to ``sys.path`` to borrow that
project's row model and table DDL so the incremental path would write rows
shaped exactly like the bulk loader's.

Both detours existed to agree with a file format. There is no such file and
no bulk loader to agree with any more: the schema in
:mod:`crossref_local._core.store` is the single declaration of a work's
shape, the primitive enforces it, and a field this module does not declare
raises rather than being silently dropped. So the engine is an ordinary
module, imported by name.

There is also no separate index to maintain. ``title`` / ``abstract`` /
``authors`` are fields on the record, written in the same upsert — which
removes the class of bug where a work was present but unsearchable because
the second write was skipped or the index had not been built.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Callable, Optional, TYPE_CHECKING

from .store import sync_state_store, works_store

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scitex_dev.store import Store

__all__ = [
    "differential_update",
    "get_last_sync_date",
    "iter_crossref_works",
    "set_sync_value",
    "upsert_work",
    "work_values",
]

# CrossRef REST works endpoint + polite-pool contact. CrossRef asks API
# users to include a ``mailto`` to join the faster "polite pool".
CROSSREF_API_URL = "https://api.crossref.org/works"
DEFAULT_MAILTO = "crossref-local@scitex.ai"
DEFAULT_ROWS = 1000

#: How many upserts share one transaction. The primitive commits per
#: operation outside a batch, and one logical upsert costs three statements,
#: so batching is worth ~9x on this workload (measured upstream).
BATCH_SIZE = 500

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Watermark helpers
# ---------------------------------------------------------------------------
def get_last_sync_date(store: "Optional[Store]" = None) -> Optional[str]:
    """Return the recorded ``last_sync_date``, or ``None`` if unset."""
    store = store if store is not None else sync_state_store()
    try:
        row = store.get({"key": "last_sync_date"})
    except Exception:
        return None
    if row is None:
        return None
    value = row.values.get("value")
    return str(value) if value else None


def set_sync_value(key: str, value: str, store: "Optional[Store]" = None) -> None:
    """Upsert one sync-state key/value pair."""
    from scitex_dev.store import ANY_REVISION

    store = store if store is not None else sync_state_store()
    store.put({"key": key, "value": value}, expected_revision=ANY_REVISION)


# ---------------------------------------------------------------------------
# CrossRef REST API fetcher (network path; injectable for tests)
# ---------------------------------------------------------------------------
# Offline feed override: when this env var points to a JSON file, pages are
# read from it instead of the network. The file is a JSON list of
# ``message`` objects (``{"items": [...], "next-cursor": ...}``) returned
# one per successive cursor. Lets callers (CI, cron dry-runs, air-gapped
# hosts) drive the real code path against a fixed feed with no network.
_FEED_ENV_VAR = "CROSSREF_LOCAL_UPDATE_FEED"


def _feed_pages() -> Optional[list]:
    """Load the offline feed pages if the feed env var is set."""
    feed_path = os.environ.get(_FEED_ENV_VAR)
    if not feed_path:
        return None
    with open(feed_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _make_feed_fetcher(pages: list) -> "Callable[[str, str, int, str], dict]":
    """Return a fetcher that serves the given feed pages in order."""
    state = {"i": 0}

    def fetch(since, cursor, rows, mailto):
        idx = min(state["i"], len(pages) - 1)
        state["i"] += 1
        return pages[idx]

    return fetch


def http_fetch_page(since: str, cursor: str, rows: int, mailto: str) -> dict:
    """Fetch one page of the CrossRef ``/works`` cursor feed.

    Returns the parsed ``message`` object, which carries ``items`` and
    ``next-cursor``. This is the ONLY function that touches the network; an
    offline feed file (``CROSSREF_LOCAL_UPDATE_FEED``) short-circuits it,
    and tests may also inject a fetcher directly.
    """
    params = {
        "filter": f"from-index-date:{since}",
        "rows": str(rows),
        "cursor": cursor,
        "mailto": mailto,
    }
    url = f"{CROSSREF_API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": mailto})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("message", {})


def iter_crossref_works(
    since: str,
    rows: int = DEFAULT_ROWS,
    mailto: str = DEFAULT_MAILTO,
    fetch_page: "Optional[Callable[[str, str, int, str], dict]]" = None,
):
    """Yield CrossRef work items via cursor deep-paging.

    Starts at ``cursor=*`` and follows ``message.next-cursor`` until a page
    returns fewer than ``rows`` items (the deep-paging terminator).

    Parameters
    ----------
    since : str
        Start date (``YYYY-MM-DD``) for the ``from-index-date`` filter.
    rows : int
        Page size requested from the API.
    mailto : str
        Polite-pool contact email.
    fetch_page : callable, optional
        Injected page fetcher ``(since, cursor, rows, mailto) -> message``.
        Defaults to :func:`http_fetch_page`. Tests pass a fake here so no
        network call is made.
    """
    if fetch_page is None:
        feed = _feed_pages()
        if feed is not None:
            fetch_page = _make_feed_fetcher(feed)
    fetch = fetch_page or http_fetch_page
    cursor = "*"
    while True:
        message = fetch(since, cursor, rows, mailto)
        items = message.get("items", [])
        for item in items:
            yield item
        # Deep-paging terminates when a page is not full.
        if len(items) < rows:
            break
        next_cursor = message.get("next-cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor


# ---------------------------------------------------------------------------
# Normalisation + upsert
# ---------------------------------------------------------------------------
def _flatten_authors(item: dict) -> str:
    """Flatten a CrossRef ``author`` list into a searchable string."""
    authors = item.get("author") or []
    names = []
    for author in authors:
        if isinstance(author, dict):
            given = author.get("given", "")
            family = author.get("family", "")
            if given or family:
                names.append(f"{given} {family}".strip())
    return " | ".join(names)


def _first(value) -> str:
    """First element of a CrossRef list-valued field, or ``""``."""
    if isinstance(value, list) and value:
        return str(value[0])
    return ""


def _published_year(item: dict) -> Optional[int]:
    """The publication year, or ``None`` when CrossRef did not give one."""
    for key in ("published", "published-print", "published-online", "issued"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def work_values(item: dict) -> Optional[dict]:
    """Map one CrossRef JSON work onto the works schema.

    Returns ``None`` for an item with no DOI — there is nothing to key it
    by, and inventing a key would put a record in the collection that no
    lookup could ever find again.

    The denormalised fields are not a cache of ``metadata``; they are what
    every non-point-lookup in this package reads. Search reads ``title`` /
    ``abstract`` / ``authors``; the impact-factor calculations read
    ``issn`` / ``year`` / ``work_type`` / ``reference_count`` /
    ``referenced_by_count``. Those used to be ``json_extract`` expressions
    evaluated by the engine on every row; the store cannot evaluate
    anything, so they are computed once here, at write time.
    """
    doi = (item.get("DOI") or "").lower()
    if not doi:
        return None

    references = item.get("reference")
    return {
        "doi": doi,
        "metadata": item,
        "title": _first(item.get("title")),
        "abstract": item.get("abstract") or "",
        "authors": _flatten_authors(item),
        "container_title": _first(item.get("container-title")),
        "issn": _first(item.get("ISSN")),
        "year": _published_year(item),
        "work_type": item.get("type") or "",
        "referenced_by_count": item.get("is-referenced-by-count") or 0,
        "reference_count": len(references) if isinstance(references, list) else 0,
    }


def upsert_work(store: "Store", item: dict) -> bool:
    """Normalise and upsert a single CrossRef work. Returns whether it wrote.

    ``ANY_REVISION`` rather than a read-then-compare: an ingest run is
    authoritative for the record it just fetched, and there is no value read
    from the store that a concurrent writer could invalidate. The compare-
    and-swap exists to protect a read-modify-write, and this is neither.
    """
    from scitex_dev.store import ANY_REVISION

    values = work_values(item)
    if values is None:
        return False
    store.put(values, expected_revision=ANY_REVISION)
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def differential_update(
    since: Optional[str] = None,
    rows: int = DEFAULT_ROWS,
    mailto: str = DEFAULT_MAILTO,
    dry_run: bool = False,
    fetch_page: "Optional[Callable[[str, str, int, str], dict]]" = None,
    store: "Optional[Store]" = None,
    sync_store: "Optional[Store]" = None,
    refresh_counts: bool = True,
) -> dict:
    """Run the incremental CrossRef update.

    Parameters
    ----------
    since : str, optional
        Override start date (``YYYY-MM-DD``). Defaults to the recorded
        watermark, else the last 7 days.
    rows : int
        API page size.
    mailto : str
        Polite-pool contact email.
    dry_run : bool
        Page the API to COUNT what would be upserted; write nothing.
    fetch_page : callable, optional
        Injected page fetcher (tests avoid the network via this).
    store, sync_store : Store, optional
        Works and sync-state stores; this host's are opened otherwise.
    refresh_counts : bool
        Recompute the exact-count cache after a successful run.

    Returns
    -------
    dict
        Statistics: ``records_upserted``, ``elapsed_seconds``,
        ``last_sync_date`` (and ``dry_run`` when applicable).
    """
    sync = sync_store if sync_store is not None else sync_state_store()

    # Resolve start date: explicit `since` > recorded watermark > 7d ago.
    if since is None:
        since = get_last_sync_date(sync)
        if since:
            logger.info("Last sync date: %s", since)
    if since is None:
        since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        logger.info("No sync history — defaulting to last 7 days (%s)", since)

    today = datetime.now().strftime("%Y-%m-%d")
    start_time = time.time()

    works = iter_crossref_works(
        since=since, rows=rows, mailto=mailto, fetch_page=fetch_page
    )

    if dry_run:
        logger.info("DRY RUN — no changes will be made.")
        count = sum(1 for item in works if (item.get("DOI") or ""))
        elapsed = time.time() - start_time
        logger.info("[dry-run] %s works would be upserted.", f"{count:,}")
        return {
            "records_upserted": count,
            "elapsed_seconds": elapsed,
            "last_sync_date": since,
            "dry_run": True,
        }

    target = store if store is not None else works_store()
    upserted = 0
    pending = 0
    batch = target.batch()
    batch.__enter__()
    try:
        for item in works:
            if upsert_work(target, item):
                upserted += 1
                pending += 1
            if pending >= BATCH_SIZE:
                batch.__exit__(None, None, None)
                logger.info("Upserted %s works...", f"{upserted:,}")
                pending = 0
                batch = target.batch()
                batch.__enter__()
    except BaseException:
        batch.__exit__(*sys.exc_info())
        raise
    else:
        batch.__exit__(None, None, None)

    # Advance the watermark ONLY after a successful pass, so an interrupted
    # run re-covers the same range (no gaps).
    set_sync_value("last_sync_date", today, sync)
    set_sync_value(
        "last_update_completed", time.strftime("%Y-%m-%d %H:%M:%S"), sync
    )
    set_sync_value("last_update_records", str(upserted), sync)

    # Refresh the exact-count cache so info() and /info report exact counts
    # without ever counting on the read path. Slow here is fine — an update
    # run already takes minutes.
    if refresh_counts:
        try:
            from .stats import refresh_stats

            refresh_stats()
            logger.info("count cache refreshed (exact counts)")
        except Exception as exc:  # noqa: BLE001 - report, do not fail the run
            logger.warning(
                "count cache NOT refreshed (%s); run `crossref-local "
                "sync-stats` manually",
                type(exc).__name__,
            )

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("Differential update complete!")
    logger.info("  Records upserted: %s", f"{upserted:,}")
    logger.info("  New last_sync_date: %s", today)
    logger.info("  Elapsed: %.1f minutes", elapsed / 60)

    return {
        "records_upserted": upserted,
        "elapsed_seconds": elapsed,
        "last_sync_date": today,
    }


def main(argv: "Optional[list[str]]" = None) -> None:
    """Command-line entry point (``python -m crossref_local._core.ingest``)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    parser = argparse.ArgumentParser(
        description="Incremental CrossRef store update (REST API)"
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Override start date (YYYY-MM-DD). Default: read from the store.",
    )
    parser.add_argument(
        "--rows", type=int, default=DEFAULT_ROWS,
        help=f"API page size (default: {DEFAULT_ROWS})",
    )
    parser.add_argument(
        "--mailto", type=str, default=DEFAULT_MAILTO,
        help="Polite-pool contact email.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count updates without writing to the store.",
    )

    args = parser.parse_args(argv)

    stats = differential_update(
        since=args.since,
        rows=args.rows,
        mailto=args.mailto,
        dry_run=args.dry_run,
    )

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()

# EOF
