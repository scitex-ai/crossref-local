"""Full-text search over the works collection.

The store primitive has no text-search surface — no ``MATCH``, no index, no
filtered read at all. :meth:`scitex_dev.store.Store.rows` is the only way to
see more than one record, and it returns every record. So matching happens
here, in Python, over the ``title`` / ``abstract`` / ``authors`` fields the
works schema denormalises for exactly this purpose.

WHAT THAT COSTS, STATED PLAINLY. This is O(collection) per query and holds
the matched slice in memory. It is correct at any size and fast only at
small ones. The production corpus is ~167M works; searching it this way is
not viable, and the fix is not a cleverer loop here — it is a query and
full-text surface on the primitive, which does not exist yet. See
``docs/adr/0001-corpus-moves-to-the-shared-store.md`` for the gap and what
closing it would require.

The query grammar is the readable subset of what callers actually wrote:
quoted phrases, bare terms, and the ``AND`` / ``OR`` / ``NOT`` operators.
It is implemented here rather than passed through to an engine, so it is
the same on every backend and cannot silently change meaning underneath a
caller.
"""

from __future__ import annotations

import re as _re
import time as _time
from typing import Callable, List, Optional, TYPE_CHECKING

from .models import LimitInfo, SearchResult, Work
from .store import works_store

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scitex_dev.store import Row, Store

__all__ = [
    "search",
    "count",
    "search_dois",
    "matches",
]

# A quoted phrase, or a bare run of non-space characters.
_TOKEN = _re.compile(r'"([^"]*)"|(\S+)')

#: Recognised as operators rather than as search terms. ``NEAR`` is accepted
#: and treated as ``AND``: proximity needs positional information this store
#: does not keep, and silently returning proximity-ordered nonsense would be
#: worse than widening the match. A caller can tell from the result count.
_OPERATORS = {"AND", "OR", "NOT", "NEAR"}


def _tokenize(query: str) -> "list[tuple[str, str]]":
    """Split ``query`` into ``(kind, value)`` pairs — ``op`` or ``term``.

    Uses ``finditer`` rather than ``findall`` DELIBERATELY, and the
    difference is not stylistic. ``findall`` on a two-group pattern yields
    ``""`` both for a group that matched nothing and for a group that did
    not participate in the match at all, so a bare word and an empty
    quoted phrase are indistinguishable in its output. Written that way,
    the quoted-phrase branch swallowed every token and EVERY UNQUOTED
    QUERY RETURNED NOTHING — searching for ``neural`` found no works while
    searching for ``"neural"`` found them. ``finditer`` gives ``None`` for
    a non-participating group, which is the distinction this needs.
    """
    tokens: list[tuple[str, str]] = []
    for match in _TOKEN.finditer(query):
        phrase, bare = match.group(1), match.group(2)
        if phrase is not None:
            if phrase.strip():
                tokens.append(("term", phrase.strip().lower()))
            continue
        upper = bare.upper()
        if upper in _OPERATORS:
            tokens.append(("op", "AND" if upper == "NEAR" else upper))
        else:
            tokens.append(("term", bare.lower()))
    return tokens


def _predicate(query: str) -> "Callable[[str], bool]":
    """Compile ``query`` into a haystack predicate.

    ``OR`` separates alternatives; within an alternative every term must be
    present, and ``NOT`` negates the term that follows it. Adjacent terms
    are joined by ``AND``, which is what the previous engine also did with
    them, so an unquoted multi-word query keeps the meaning it had.

    An empty query matches nothing rather than everything. Returning every
    work for ``""`` would turn a caller's missing input into a full-corpus
    read, which is the most expensive thing this module can do.
    """
    tokens = _tokenize(query)
    if not tokens:
        return lambda _haystack: False

    alternatives: list[list[tuple[bool, str]]] = [[]]
    negate_next = False
    for kind, value in tokens:
        if kind == "op":
            if value == "OR":
                alternatives.append([])
            elif value == "NOT":
                negate_next = True
            # AND is the default join; nothing to record.
            continue
        alternatives[-1].append((negate_next, value))
        negate_next = False

    clauses = [clause for clause in alternatives if clause]
    if not clauses:
        return lambda _haystack: False

    def predicate(haystack: str) -> bool:
        for clause in clauses:
            if all(
                (term not in haystack) if negated else (term in haystack)
                for negated, term in clause
            ):
                return True
        return False

    return predicate


def _haystack(row: "Row") -> str:
    """The searchable text of one work, lowercased."""
    values = row.values
    parts = (
        values.get("title") or "",
        values.get("abstract") or "",
        values.get("authors") or "",
        values.get("container_title") or "",
    )
    return " ".join(parts).lower()


def matches(query: str, store: "Optional[Store]" = None) -> "List[Row]":
    """Every work matching ``query``, ordered by DOI.

    Ordering is imposed here and is not the store's. ``Store.rows()`` makes
    no ordering promise, so paginating on its natural order would let the
    same offset return different works between calls — which is how a
    caller paging through results silently skips some and repeats others.
    """
    store = store if store is not None else works_store()
    predicate = _predicate(query)
    hits = [row for row in store.rows() if predicate(_haystack(row))]
    hits.sort(key=lambda row: str(row.values.get("doi") or ""))
    return hits


def search(
    query: str,
    limit: int = 10,
    offset: int = 0,
    store: "Optional[Store]" = None,
) -> SearchResult:
    """
    Full-text search across works.

    Args:
        query: Search query (supports ``AND``, ``OR``, ``NOT``, "phrases")
        limit: Maximum results to return
        offset: Skip first N results (for pagination)
        store: Works store (opens this host's if not provided)

    Returns:
        SearchResult with matching works

    Example:
        >>> results = search("hippocampal sharp wave ripples")
        >>> print(f"Found {results.total} matches in {results.elapsed_ms:.1f}ms")
        >>> for work in results:
        ...     print(f"{work.title} ({work.year})")
    """
    start = _time.perf_counter()

    hits = matches(query, store)
    total = len(hits)
    page = hits[offset : offset + limit] if limit >= 0 else hits[offset:]

    works = [
        Work.from_metadata(
            str(row.values.get("doi")), row.values.get("metadata") or {}
        )
        for row in page
    ]

    elapsed_ms = (_time.perf_counter() - start) * 1000

    returned = len(works)
    capped = returned < total and returned == limit
    capped_reason = None
    if capped:
        capped_reason = (
            f"crossref-local: Limited to {limit} results (total available: {total})"
        )

    limit_info = LimitInfo(
        requested=limit,
        returned=returned,
        total_available=total,
        capped=capped,
        capped_reason=capped_reason,
        stage="crossref-local",
    )

    return SearchResult(
        works=works,
        total=total,
        query=query,
        elapsed_ms=elapsed_ms,
        limit_info=limit_info,
    )


def count(query: str, store: "Optional[Store]" = None) -> int:
    """
    Count matching works without building ``Work`` objects.

    Cheaper than :func:`search` only in object construction — the scan is
    the same, because the store cannot count a subset for us.

    Args:
        query: Search query
        store: Works store

    Returns:
        Number of matching works
    """
    return len(matches(query, store))


def search_dois(
    query: str,
    limit: int = 1000,
    store: "Optional[Store]" = None,
) -> List[str]:
    """
    Search and return only DOIs.

    Args:
        query: Search query
        limit: Maximum DOIs to return
        store: Works store

    Returns:
        List of matching DOIs
    """
    hits = matches(query, store)
    return [str(row.values.get("doi")) for row in hits[:limit]]


# Explicit-store versions for the async API, which runs these on a worker
# thread with that thread's own store.
def _search_with_store(
    store: "Store", query: str, limit: int, offset: int
) -> SearchResult:
    """Search with an explicit store (for thread-safe async)."""
    return search(query, limit, offset, store=store)


def _count_with_store(store: "Store", query: str) -> int:
    """Count with an explicit store (for thread-safe async)."""
    return count(query, store=store)

# EOF
