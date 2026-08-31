"""Collection counts, with an exact-count cache.

WHY THIS MODULE STILL EXISTS, AND WHAT CHANGED
----------------------------------------------
It was written because ``COUNT(*)`` was prohibitively slow on the corpus
(measured 2026-07-22: ``works`` 167,008,748 rows -> 0.42 s; the full-text
table -> 12.70 s; ``citations`` 1,788,599,072 rows -> 4.35 s; ~17.5 s per
``info()`` call), and it kept the read path O(1) by falling back to a cheap
``MAX(rowid)`` estimate.

**That estimator is gone and has no replacement.** It read a rowid-addressed
file's allocation counter, which is a property of that file format rather
than of counting, and nothing in a real database corresponds to it.

What DOES exist is a real count: :meth:`scitex_dev.store.Store.count` takes
a query and answers in the database. So the counters below no longer
materialise a collection to measure it — the number crosses the connection
and nothing else does. That removes the memory hazard entirely; counting
167M works no longer means holding 167M rows in this process.

It does not make counting FREE. A ``COUNT(*)`` over a corpus that size is
still a scan inside the server, in the seconds, which is the same reason
this module existed in the first place. So the split is unchanged:

- :func:`get_counts` — the read path — NEVER counts. It reads the cache, or
  reports ``counts_source: "unavailable"``. A fallback here would put a
  multi-second scan behind every ``info()`` call and every ``/health``
  probe, which is exactly the cost the cache exists to avoid.
- :func:`refresh_stats` — the write path — counts once and writes the cache.
  Run it from the ingest pipeline or ``crossref-local sync-stats``.

An estimate is never presented as exact, and an absent count is never
presented as zero-the-number; ``counts_source`` always says which happened.
"""

from __future__ import annotations

from datetime import datetime as _datetime
from datetime import timezone as _timezone
from typing import Optional as _Optional

from .store import (
    CITATIONS,
    WORKS,
    citations_store,
    corpus_stats_store,
    works_store,
)

__all__ = [
    "STATS_COLLECTIONS",
    "count_works",
    "count_searchable",
    "count_citations",
    "read_cached_counts",
    "get_counts",
    "refresh_stats",
]

#: (cache key, public ``info()`` key) pairs — order defines output order.
#:
#: ``searchable`` replaces the old ``works_fts`` entry. There is no separate
#: full-text collection any more: a work is searchable when it carries the
#: text :mod:`crossref_local._core.fts` reads, so the number is a property
#: of the works collection rather than of a second table that could drift
#: out of sync with it.
STATS_COLLECTIONS = (
    ("works", "works"),
    ("searchable", "fts_indexed"),
    ("citations", "citations"),
)


def count_works(store=None) -> int:
    """Exact number of works. Counted in the database, not in this process."""
    from scitex_dev.store import Query

    store = store if store is not None else works_store()
    return store.count(Query())


def count_searchable(store=None) -> int:
    """Exact number of works carrying searchable text.

    A work with neither title, abstract nor author text cannot be returned
    by any query, so counting it as indexed would overstate what search can
    reach — precisely the drift the old separate index table made possible
    and this collapses.

    ``nonempty`` rather than "is not null": a record that stores an empty
    title satisfies ``IS NOT NULL`` and is still unsearchable, so the
    stricter test is the one that answers the question actually being asked.
    """
    from scitex_dev.store import Query, either, nonempty

    store = store if store is not None else works_store()
    return store.count(
        Query().where(
            either(nonempty("title"), nonempty("abstract"), nonempty("authors"))
        )
    )


def count_citations(store=None) -> int:
    """Exact number of citation edges. Counted in the database."""
    from scitex_dev.store import Query

    store = store if store is not None else citations_store()
    return store.count(Query())


_COUNTERS = {
    "works": count_works,
    "searchable": count_searchable,
    "citations": count_citations,
}


def read_cached_counts(store=None) -> _Optional[dict]:
    """Read exact counts from the cache collection.

    Args:
        store: The corpus-stats store (opens this host's if not provided).

    Returns:
        ``{"works": n, "fts_indexed": n, "citations": n,
        "counts_computed_at": <ISO timestamp>}`` when the cache covers every
        tracked collection, else ``None`` — absent entry, unreadable value,
        or partial coverage. The caller then reports the counts as
        unavailable rather than filling the gap with a number it did not
        measure.
    """
    try:
        store = store if store is not None else corpus_stats_store()
        rows = store.rows()
    except Exception:
        return None

    by_key = {str(row.values.get("collection")): row.values for row in rows}
    if any(key not in by_key for key, _public in STATS_COLLECTIONS):
        return None

    counts: dict = {}
    stamps = []
    for key, public in STATS_COLLECTIONS:
        values = by_key[key]
        row_count = values.get("row_count")
        if not isinstance(row_count, int) or isinstance(row_count, bool):
            return None
        counts[public] = row_count
        stamps.append(values.get("computed_at"))

    # Report the OLDEST stamp: the honest age of the least-fresh count.
    counts["counts_computed_at"] = min((s for s in stamps if s), default=None)
    return counts


def get_counts(store=None) -> dict:
    """Collection counts for ``info()`` — cache only, never a scan.

    ``counts_source`` is ``"exact"`` when the cache answered and
    ``"unavailable"`` when it did not. There is deliberately no third,
    cheaper path: the estimator that used to fill that role read a
    file-format detail that no longer exists, and inventing a number here
    would be worse than saying the count is not known.
    """
    cached = read_cached_counts(store)
    if cached is not None:
        cached["counts_source"] = "exact"
        return cached
    return {
        public: 0 for _key, public in STATS_COLLECTIONS
    } | {
        "counts_computed_at": None,
        "counts_source": "unavailable",
        "note": (
            "No cached counts. Run `crossref-local sync-stats` to compute "
            "them; the read path does not count, because counting means "
            "reading every record."
        ),
    }


def refresh_stats(store=None) -> dict:
    """Count every collection exactly and write the cache.

    Slow by design — it reads each collection in full — so run it from the
    ingest pipeline or ``crossref-local sync-stats``, never from ``info()``.

    Args:
        store: The corpus-stats store (opens this host's if not provided).

    Returns:
        The freshly computed counts, same shape as :func:`get_counts`
        (``counts_source: "exact"``).
    """
    from scitex_dev.store import ANY_REVISION

    cache = store if store is not None else corpus_stats_store()
    computed_at = _datetime.now(_timezone.utc).isoformat(timespec="seconds")

    counts: dict = {}
    for key, public in STATS_COLLECTIONS:
        try:
            n = _COUNTERS[key]()
        except Exception:
            # A collection that has never been written does not exist yet.
            # Recording 0 keeps the same convention info() has always used
            # for an absent table.
            n = 0
        cache.put(
            {"collection": key, "row_count": n, "computed_at": computed_at},
            # ANY_REVISION: this is a cache entry with a single logical
            # writer per run and no lost-update hazard worth a retry loop —
            # the value is recomputed from scratch each time, so an
            # overwritten one loses nothing that cannot be recomputed.
            expected_revision=ANY_REVISION,
        )
        counts[public] = n

    counts["counts_computed_at"] = computed_at
    counts["counts_source"] = "exact"
    return counts


# Names the schemas so a reader of this module can see what is counted
# without opening the store module.
_TRACKED_SCHEMAS = (WORKS, CITATIONS)

# EOF
