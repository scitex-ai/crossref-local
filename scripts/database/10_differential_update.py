#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Differential (incremental) update for the CrossRef local database.

Incrementally refreshes the local ``works`` table from the CrossRef REST
API instead of the ~1.5 TB Public Data File dump. Only works whose
``from-index-date`` is newer than the recorded last sync date are
fetched and upserted (INSERT OR REPLACE), mirroring the shape of
openalex-local's ``10_differential_update.py`` sync engine.

Usage:
    python 10_differential_update.py [--db-path PATH]
    python 10_differential_update.py --since 2026-03-01
    python 10_differential_update.py --dry-run

Steps:
    1. Read last sync date from the ``_metadata`` table (created if absent).
    2. Deep-page the CrossRef REST API from ``from-index-date=<since>``
       (cursor=* -> message.next-cursor until a short page is returned).
    3. Normalise each CrossRef JSON work into a ``works`` row (reusing
       the vendored dois2sqlite ``Record`` model + mapping) and UPSERT it.
    4. Refresh the ``works_fts`` FTS5 index for the upserted rows.
    5. Advance ``_metadata.last_sync_date`` ONLY after a successful run
       (an interrupted run therefore re-covers the same range — no gaps).
"""

import argparse
import json
import logging
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

# Reuse the vendored dois2sqlite ``Record`` model + works-table DDL so the
# incremental path writes rows shaped IDENTICALLY to the bulk loader. We do
# NOT import ``dois2sqlite.database.generate_metadata_record`` directly
# because ``dois2sqlite.database`` eagerly imports ``representations`` ->
# ``commonmeta`` (a heavy optional dep only used by its commonmeta branch,
# which the incremental path never takes). Instead we reuse ``Record`` and
# ``create_works_table`` and replicate dois2sqlite's non-commonmeta mapping
# verbatim in ``generate_metadata_record`` below.
_VENDOR_DIR = (
    Path(__file__).resolve().parents[2] / "vendor" / "dois2sqlite"
)
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from dois2sqlite.models import Record  # noqa: E402


def create_works_table(cursor: sqlite3.Cursor) -> None:
    """Create the ``works`` table (verbatim from dois2sqlite.database).

    Copied rather than imported because ``dois2sqlite.database`` eagerly
    pulls in ``commonmeta`` (see note above). The DDL is identical to the
    bulk loader's, so both paths share one schema.
    """
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS works ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, doi VARCHAR(255), "
        "resource_primary_url VARCHAR(255), type VARCHAR(255), "
        "member INTEGER, prefix VARCHAR(8), created_date_time DATE, "
        "deposited_date_time DATE, commonmeta_format BOOLEAN, metadata BLOB)"
    )


def generate_metadata_record(item: dict, convert_to_commonmeta: bool = False):
    """Map a CrossRef JSON work to a dois2sqlite ``Record``.

    Byte-for-byte mirror of ``dois2sqlite.database.generate_metadata_record``
    for the ``convert_to_commonmeta=False`` case (the only case the
    incremental sync uses), avoiding that module's eager ``commonmeta``
    import. The commonmeta branch is intentionally unsupported here.
    """
    if convert_to_commonmeta:
        raise NotImplementedError(
            "commonmeta conversion is not supported in the incremental path"
        )
    metadata = item
    return Record(
        item.get("DOI", "").lower(),
        item.get("resource", {}).get("primary", {}).get("URL", ""),
        item.get("type", ""),
        item.get("member", 0),
        item.get("prefix", ""),
        item.get("created", {}).get("date-time", ""),
        item.get("deposited", {}).get("date-time", ""),
        False,
        json.dumps(metadata),
    )

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "crossref.db"

# CrossRef REST works endpoint + polite-pool contact. CrossRef asks
# API users to include a ``mailto`` to join the faster "polite pool".
CROSSREF_API_URL = "https://api.crossref.org/works"
DEFAULT_MAILTO = "crossref-local@scitex.ai"
DEFAULT_ROWS = 1000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metadata helpers (mirror openalex-local's _metadata contract)
# ---------------------------------------------------------------------------
def ensure_metadata_table(conn: sqlite3.Connection) -> None:
    """Create the key/value ``_metadata`` table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.commit()


def get_last_sync_date(conn: sqlite3.Connection) -> Optional[str]:
    """Return the recorded ``last_sync_date`` or ``None`` if unset."""
    try:
        cursor = conn.execute(
            "SELECT value FROM _metadata WHERE key = 'last_sync_date'"
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def set_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a single ``_metadata`` key/value pair."""
    conn.execute(
        "INSERT OR REPLACE INTO _metadata (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# CrossRef REST API fetcher (network path; injectable for tests)
# ---------------------------------------------------------------------------
# Offline feed override: when this env var points to a JSON file, pages
# are read from it instead of the network. The file is a JSON list of
# ``message`` objects (``{"items": [...], "next-cursor": ...}``) returned
# one per successive cursor. Lets callers (CI, cron dry-runs, air-gapped
# hosts) drive the real code path against a fixed feed with no network.
_FEED_ENV_VAR = "CROSSREF_LOCAL_UPDATE_FEED"


def _feed_pages() -> Optional[list]:
    """Load the offline feed pages if the feed env var is set."""
    feed_path = _os_environ_get(_FEED_ENV_VAR)
    if not feed_path:
        return None
    with open(feed_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _os_environ_get(key: str) -> Optional[str]:
    """Thin ``os.environ.get`` shim (kept local to ease import ordering)."""
    import os

    return os.environ.get(key)


def _make_feed_fetcher(pages: list) -> Callable[[str, str, int, str], dict]:
    """Return a fetcher that serves the given feed pages in order."""
    state = {"i": 0}

    def fetch(since, cursor, rows, mailto):
        idx = min(state["i"], len(pages) - 1)
        state["i"] += 1
        return pages[idx]

    return fetch


def http_fetch_page(
    since: str,
    cursor: str,
    rows: int,
    mailto: str,
) -> dict:
    """Fetch one page of the CrossRef ``/works`` cursor feed.

    Returns the parsed ``message`` object, which carries ``items`` and
    ``next-cursor``. This is the ONLY function that touches the network;
    an offline feed file (``CROSSREF_LOCAL_UPDATE_FEED``) short-circuits
    it, and tests may also inject a fetcher directly.
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
    fetch_page: Optional[Callable[[str, str, int, str], dict]] = None,
):
    """Yield CrossRef work items via cursor deep-paging.

    Starts at ``cursor=*`` and follows ``message.next-cursor`` until a
    page returns fewer than ``rows`` items (the deep-paging terminator).

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
# Upsert + FTS
# ---------------------------------------------------------------------------
def upsert_work(conn: sqlite3.Connection, item: dict) -> None:
    """Normalise + UPSERT a single CrossRef work into ``works``.

    Reuses dois2sqlite's ``generate_metadata_record`` so the row shape
    matches the bulk loader exactly, then INSERT OR REPLACE keyed on
    ``doi`` (uniqueness enforced by ``upsert_delete_existing``).
    """
    record = generate_metadata_record(item, convert_to_commonmeta=False)
    if not record.doi:
        return
    # INSERT OR REPLACE needs a UNIQUE key; ``works`` is keyed on an
    # autoincrement id, so delete any prior row for this DOI first to
    # keep the table free of duplicates on re-sync.
    conn.execute("DELETE FROM works WHERE doi = ?", (record.doi,))
    conn.execute(
        """
        INSERT INTO works (
            doi, resource_primary_url, type, member, prefix,
            created_date_time, deposited_date_time, commonmeta_format,
            metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.doi,
            record.resource_primary_url,
            record.type,
            record.member,
            record.prefix,
            record.created_date_time,
            record.deposited_date_time,
            record.commonmeta_format,
            record.metadata,
        ),
    )


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


def update_fts_for_work(conn: sqlite3.Connection, item: dict) -> None:
    """Refresh the contentless ``works_fts`` row for one work.

    ``works_fts`` is a contentless FTS5 table (``content=''``), so the
    ``'rebuild'`` command does not apply — instead delete any stale row
    for the DOI and re-insert. Skipped silently if the FTS table has not
    been built yet.
    """
    doi = (item.get("DOI") or "").lower()
    if not doi:
        return
    try:
        conn.execute("DELETE FROM works_fts WHERE doi = ?", (doi,))
        title_list = item.get("title") or []
        title = title_list[0] if title_list else ""
        abstract = item.get("abstract") or ""
        authors = _flatten_authors(item)
        conn.execute(
            "INSERT INTO works_fts(doi, title, abstract, authors) "
            "VALUES (?, ?, ?, ?)",
            (doi, title, abstract, authors),
        )
    except sqlite3.OperationalError:
        # FTS index not built on this DB — nothing to keep in sync.
        pass


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def differential_update(
    db_path: Path,
    since: Optional[str] = None,
    rows: int = DEFAULT_ROWS,
    mailto: str = DEFAULT_MAILTO,
    dry_run: bool = False,
    rebuild_fts: bool = True,
    fetch_page: Optional[Callable[[str, str, int, str], dict]] = None,
) -> dict:
    """Run the incremental CrossRef update.

    Parameters
    ----------
    db_path : Path
        Path to the SQLite database.
    since : str, optional
        Override start date (``YYYY-MM-DD``). Defaults to the DB's
        recorded ``_metadata.last_sync_date`` (else the last 7 days).
    rows : int
        API page size.
    mailto : str
        Polite-pool contact email.
    dry_run : bool
        Page the API to COUNT what would be upserted; write nothing.
    rebuild_fts : bool
        Keep ``works_fts`` in sync for upserted rows.
    fetch_page : callable, optional
        Injected page fetcher (tests avoid the network via this).

    Returns
    -------
    dict
        Statistics: ``records_upserted``, ``elapsed_seconds``,
        ``last_sync_date`` (and ``dry_run`` when applicable).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    ensure_metadata_table(conn)
    create_works_table(conn.cursor())

    # Resolve start date: explicit --since > recorded last sync > 7d ago.
    if since is None:
        since = get_last_sync_date(conn)
        if since:
            logger.info(f"Last sync date: {since}")
    if since is None:
        since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        logger.info(f"No sync history — defaulting to last 7 days ({since})")

    today = datetime.now().strftime("%Y-%m-%d")
    start_time = time.time()

    works = iter_crossref_works(
        since=since, rows=rows, mailto=mailto, fetch_page=fetch_page
    )

    if dry_run:
        logger.info("DRY RUN — no changes will be made.")
        count = sum(1 for _ in works)
        conn.close()
        elapsed = time.time() - start_time
        logger.info(f"[dry-run] {count:,} works would be upserted.")
        return {
            "records_upserted": count,
            "elapsed_seconds": elapsed,
            "last_sync_date": since,
            "dry_run": True,
        }

    upserted = 0
    for item in works:
        upsert_work(conn, item)
        if rebuild_fts:
            update_fts_for_work(conn, item)
        upserted += 1
        if upserted % 1000 == 0:
            conn.commit()
            logger.info(f"Upserted {upserted:,} works...")
    conn.commit()

    # Advance the sync watermark ONLY after a successful pass, so an
    # interrupted run re-covers the same range (no gaps).
    set_metadata(conn, "last_sync_date", today)
    set_metadata(
        conn, "last_update_completed", time.strftime("%Y-%m-%d %H:%M:%S")
    )
    set_metadata(conn, "last_update_records", str(upserted))
    conn.close()

    # Refresh the db_stats exact-count cache so info() / the /info
    # endpoint report exact counts without ever running COUNT(*)
    # themselves (~17.5 s on the production DB). Slow here is fine —
    # an update run already takes minutes.
    try:
        from crossref_local._core.stats import refresh_stats

        refresh_stats(db_path)
        logger.info("db_stats cache refreshed (exact counts)")
    except ImportError:
        logger.warning(
            "crossref_local not importable — db_stats cache NOT "
            "refreshed; run `crossref-local refresh-stats` manually"
        )

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("Differential update complete!")
    logger.info(f"  Records upserted: {upserted:,}")
    logger.info(f"  New last_sync_date: {today}")
    logger.info(f"  Elapsed: {elapsed / 60:.1f} minutes")

    return {
        "records_upserted": upserted,
        "elapsed_seconds": elapsed,
        "last_sync_date": today,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Incremental CrossRef database update (REST API)"
    )
    parser.add_argument(
        "--db-path", type=Path, default=DEFAULT_DB_PATH,
        help=f"Database path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Override start date (YYYY-MM-DD). Default: read from DB.",
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
        help="Count updates without writing to the database.",
    )
    parser.add_argument(
        "--no-fts", action="store_true",
        help="Skip FTS index maintenance for upserted rows.",
    )

    args = parser.parse_args()

    stats = differential_update(
        db_path=args.db_path,
        since=args.since,
        rows=args.rows,
        mailto=args.mailto,
        dry_run=args.dry_run,
        rebuild_fts=not args.no_fts,
    )

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()

# EOF
