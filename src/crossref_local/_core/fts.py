"""Full-text search over the works collection.

Search is served by the store's own indexed full-text surface — a GIN index
over the `title` / `abstract` / `authors` / `container_title` fields the
works schema declares as `text_search`. Matching, ordering and paging all
happen in the database; nothing here reads the collection to narrow it.

WHY THERE IS A TRANSLATION STEP. The store compiles a text criterion to
PostgreSQL's `websearch_to_tsquery`, whose negation operator is a leading
`-` and which, under the `english` configuration, silently discards `AND`,
`OR` and `NOT` as stopwords. This package's published grammar has used the
spelled-out operators since its first release. Passing a query through
unchanged would therefore not fail — it would quietly mean something else:
`editing NOT gene` would drop the `NOT`, become `editing & gene`, and return
the exact opposite of what was asked, with nothing anywhere to say so.

So the grammar is parsed here and re-emitted in websearch form. The
translation is the whole of the coupling: everything after it is the
engine's, including the index.

WHAT CHANGED FOR CALLERS. Matching is now by stemmed WORD rather than by
substring, which is what the retired engine's index did too — `editing`
finds `edited`, and `neur` no longer matches `neural`. That is a return to
the documented behaviour rather than a departure from it.
"""

from __future__ import annotations

import re as _re
import time as _time
from typing import List, Optional, TYPE_CHECKING

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
#: and treated as ``AND``: proximity needs positional information the text
#: index does not keep, and silently returning proximity-ordered nonsense
#: would be worse than widening the match.
_OPERATORS = {"AND", "OR", "NOT", "NEAR"}

#: Results are ordered by DOI. The store appends the record key to every
#: ORDER BY as a final tie-break, so paging is deterministic either way —
#: but an explicit key means two callers asking the same question get the
#: same page, rather than whatever order the index happened to produce.
_ORDER_FIELD = "doi"


def _tokenize(query: str) -> "list[tuple[str, str]]":
    """Split ``query`` into ``(kind, value)`` pairs — ``op`` or ``term``.

    Uses ``finditer`` rather than ``findall`` DELIBERATELY, and the
    difference is not stylistic. ``findall`` on a two-group pattern yields
    ``""`` both for a group that matched nothing and for a group that did
    not participate in the match at all, so a bare word and an empty quoted
    phrase are indistinguishable in its output. Written that way, the
    quoted-phrase branch swallowed every token and EVERY UNQUOTED QUERY
    RETURNED NOTHING — searching for ``neural`` found no works while
    searching for ``"neural"`` found them. ``finditer`` gives ``None`` for a
    non-participating group, which is the distinction this needs.
    """
    tokens: list[tuple[str, str]] = []
    for match in _TOKEN.finditer(query):
        phrase, bare = match.group(1), match.group(2)
        if phrase is not None:
            if phrase.strip():
                tokens.append(("term", phrase.strip()))
            continue
        upper = bare.upper()
        if upper in _OPERATORS:
            tokens.append(("op", "AND" if upper == "NEAR" else upper))
        else:
            tokens.append(("term", bare))
    return tokens


def _websearch_query(query: str) -> "str | None":
    """Re-emit this package's grammar in ``websearch_to_tsquery`` form.

    ``AND`` is the default join and is simply dropped; ``OR`` is passed
    through as the lowercase word the parser recognises; ``NOT x`` becomes
    ``-x``. A multi-word phrase is re-quoted so it stays a phrase.

    Returns ``None`` for a query with no searchable terms, which the callers
    turn into an empty result. That is deliberate and is NOT what the store
    would do: ``Query.matching(None)`` CLEARS the criterion, so handing a
    blank query straight through would return the entire collection. An
    empty search box must not read the corpus.
    """
    tokens = _tokenize(query)
    if not tokens:
        return None

    parts: list[str] = []
    negate_next = False
    for kind, value in tokens:
        if kind == "op":
            if value == "OR":
                parts.append("or")
            elif value == "NOT":
                negate_next = True
            # AND is the implicit join; emitting it would make the parser
            # treat it as a stopword and drop it, which is the same thing.
            continue
        term = f'"{value}"' if (" " in value or not value) else value
        parts.append(f"-{term}" if negate_next else term)
        negate_next = False

    # A query that was nothing but operators has no terms to match.
    if not any(part != "or" for part in parts):
        return None
    return " ".join(parts)


def _query_for(query: str, *, limit: "int | None" = None, offset: int = 0):
    """Build the store query for ``query``, or ``None`` if it matches nothing."""
    from scitex_dev.store import Query

    text = _websearch_query(query)
    if text is None:
        return None
    built = Query().matching(text).ordered_by(_ORDER_FIELD, descending=False)
    if limit is not None:
        built = built.limited(limit, offset=offset)
    elif offset:
        built = built.limited(None, offset=offset)
    return built


def matches(query: str, store: "Optional[Store]" = None) -> "List[Row]":
    """Every work matching ``query``, ordered by DOI.

    Kept for callers that want the rows rather than :class:`Work` objects.
    Unlike :func:`search` this applies no limit, so it materialises every
    match — prefer ``search`` with a limit when the count may be large.
    """
    built = _query_for(query)
    if built is None:
        return []
    store = store if store is not None else works_store()
    return store.search(built)


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

    store = store if store is not None else works_store()
    paged = _query_for(query, limit=limit, offset=offset)

    if paged is None:
        total = 0
        rows: "List[Row]" = []
    else:
        # Two statements rather than one: the total is the size of the whole
        # match, not of the page, and asking the database for it is cheaper
        # than fetching every row to measure it.
        total = store.count(_query_for(query))
        rows = store.search(paged)

    works = [
        Work.from_metadata(
            str(row.values.get("doi")), row.values.get("metadata") or {}
        )
        for row in rows
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
    Count matching works without fetching them.

    Genuinely cheaper than :func:`search` now: the count happens in the
    database and no row crosses the connection.

    Args:
        query: Search query
        store: Works store

    Returns:
        Number of matching works
    """
    built = _query_for(query)
    if built is None:
        return 0
    store = store if store is not None else works_store()
    return store.count(built)


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
    built = _query_for(query, limit=limit)
    if built is None:
        return []
    store = store if store is not None else works_store()
    return [str(row.values.get("doi")) for row in store.search(built)]


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
