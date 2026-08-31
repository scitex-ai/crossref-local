#!/usr/bin/env python3
"""Journal lookup: name -> ISSN, and ISSN -> OpenAlex journal metadata.

Everything here reads the ``crossref_journals`` collection through
:func:`crossref_local._core.store.journals_store`. The store primitive has
no filtered read, no join and no ordering, so selection and ranking happen
in Python over :meth:`~scitex_dev.store.Store.rows`.

Two things the previous implementation did have gone away:

*No table feature-detection.* It probed the engine's own catalog to decide
whether ``journals_openalex`` and ``issn_lookup`` existed, and branched on
the answer. A collection always exists once its schema is declared, so the
question "does the table exist" has no meaning here. The question that
still has meaning is "has anything been written to it", and that is asked
directly — an empty :meth:`~scitex_dev.store.Store.rows` — at the one place
it changes behaviour (:meth:`JournalLookup.get_issn` falls back to scanning
works).

*No join table.* Alternate ISSNs live in the ``issns`` list on the journal
record itself, so an ISSN that is not the ISSN-L is found by looking inside
that list rather than by joining a second table.

WHAT THAT COSTS, STATED PLAINLY. Every lookup that is not a point read on
the ISSN-L reads the whole journal collection (~222k records at the size
this was written for). The fallback that scans works is far worse and is
only reached when the journal collection is empty.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .._core.store import journals_store, works_store

logger = logging.getLogger(__name__)

__all__ = [
    "JournalLookup",
    "impact_factor_for_issn",
    "impact_factor_index",
]


def _works_count(values) -> int:
    """``works_count`` as a sortable integer.

    A missing count sorts last rather than raising: ``sorted`` cannot
    compare ``None`` with ``int``, and one record with an unwritten count
    would otherwise break ranking for every caller.
    """
    count = values.get("works_count")
    return count if isinstance(count, int) and not isinstance(count, bool) else -1


def _issns_of(values) -> List[str]:
    """Every ISSN a journal record answers to — its ISSN-L and its list."""
    out: List[str] = []
    issn_l = values.get("issn_l")
    if issn_l:
        out.append(str(issn_l))
    issns = values.get("issns")
    if isinstance(issns, list):
        out.extend(str(issn) for issn in issns if issn)
    return out


class JournalLookup:
    """Journal name / ISSN resolution over the journal collection.

    Thread-safe by construction when no store is passed: the openers in
    :mod:`crossref_local._core.store` hand out one store per thread, so two
    threads never share a connection.

    Args:
        store: The journal collection (opens this thread's if not given).
        works: The works collection, used only by the slow fallback below
            (opens this thread's if not given).
    """

    def __init__(self, store=None, *, works=None):
        self._store = store
        self._works = works

    def _journals(self):
        return self._store if self._store is not None else journals_store()

    def _works_collection(self):
        return self._works if self._works is not None else works_store()

    # -- name -> ISSN ----------------------------------------------------

    def get_issn(self, journal_name: str, strict: bool = True) -> Optional[str]:
        """
        Get ISSN for a journal name.

        Args:
            journal_name: Journal name (case-insensitive)
            strict: If True, only exact matches. If False, allow partial
                matches, ranked by ``works_count``.

        Returns:
            ISSN string or None if not found
        """
        rows = self._journals().rows()
        if not rows:
            logger.warning(
                "Journal collection is empty. Load the OpenAlex journal "
                "data for fast lookups; falling back to a works scan."
            )
            return self._get_issn_from_works(journal_name, strict)

        target = journal_name.lower()

        for row in rows:
            if (row.values.get("name_lower") or "") == target:
                issn = row.values.get("issn_l")
                if issn:
                    return str(issn)

        if strict:
            logger.debug("Strict mode: no exact match for '%s'", journal_name)
            return None

        logger.warning(
            "Using partial match for '%s' - results may be inaccurate",
            journal_name,
        )
        partial = [
            row
            for row in rows
            if target in (row.values.get("name_lower") or "")
            and row.values.get("issn_l")
        ]
        if not partial:
            return None
        partial.sort(key=lambda row: _works_count(row.values), reverse=True)
        best = partial[0].values
        logger.warning("  Matched to: '%s'", best.get("name"))
        return str(best.get("issn_l"))

    def _get_issn_from_works(
        self, journal_name: str, strict: bool = True
    ) -> Optional[str]:
        """Slow fallback: find an ISSN by scanning the works collection.

        Reads every work. Only reached when the journal collection has
        never been populated.
        """
        target = journal_name if strict else journal_name.lower()
        for row in self._works_collection().rows():
            values = row.values
            container = values.get("container_title") or ""
            issn = values.get("issn")
            if not issn:
                continue
            if strict:
                if container == target:
                    return str(issn)
            elif target in container.lower():
                return str(issn)
        return None

    # -- search / metadata -----------------------------------------------

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for journals by name.

        Args:
            query: Search query (partial name match, case-insensitive)
            limit: Maximum results to return

        Returns:
            List of journal info dictionaries with IF proxy, most
            prolific journals first. Empty when nothing matches — which is
            also the answer when the journal collection has never been
            populated.
        """
        needle = query.lower()
        hits = [
            row
            for row in self._journals().rows()
            if needle in (row.values.get("name_lower") or "")
        ]
        hits.sort(key=lambda row: _works_count(row.values), reverse=True)

        return [
            {
                "name": row.values.get("name"),
                "issn": row.values.get("issn_l"),
                "publisher": row.values.get("publisher"),
                "works_count": row.values.get("works_count"),
                "if_proxy": row.values.get("two_year_mean_citedness"),
                "h_index": row.values.get("h_index"),
            }
            for row in hits[:limit]
        ]

    def get_info(self, issn: str) -> Optional[Dict]:
        """
        Get journal info by ISSN.

        Tries the ISSN-L point read first — the only O(1) read the store
        offers — and otherwise looks for a record whose ``issns`` list
        carries this ISSN, which reads the whole collection.

        Args:
            issn: Journal ISSN (ISSN-L or any alternate)

        Returns:
            Journal info dictionary with IF proxy or None
        """
        journals = self._journals()
        row = journals.get({"issn_l": issn})

        if row is None:
            for candidate in journals.rows():
                if issn in _issns_of(candidate.values):
                    row = candidate
                    break

        if row is None:
            return None

        values = row.values
        issns = values.get("issns")
        return {
            "name": values.get("name"),
            "issn": values.get("issn_l"),
            "issns": list(issns) if isinstance(issns, list) else [],
            "publisher": values.get("publisher"),
            "works_count": values.get("works_count"),
            "if_proxy": values.get("two_year_mean_citedness"),
            "h_index": values.get("h_index"),
            "is_oa": values.get("is_oa"),
        }

    def get_if_proxy(
        self, journal_name: str, strict: bool = True
    ) -> Optional[float]:
        """
        Get OpenAlex Impact Factor proxy for a journal.

        Args:
            journal_name: Journal name
            strict: If True, only exact matches

        Returns:
            2-year mean citedness (IF proxy) or None
        """
        rows = self._journals().rows()
        target = journal_name.lower()

        for row in rows:
            if (row.values.get("name_lower") or "") == target:
                proxy = row.values.get("two_year_mean_citedness")
                if proxy:
                    return proxy

        if strict:
            return None

        partial = [
            row
            for row in rows
            if target in (row.values.get("name_lower") or "")
            and row.values.get("two_year_mean_citedness")
        ]
        if not partial:
            return None
        partial.sort(key=lambda row: _works_count(row.values), reverse=True)
        return partial[0].values.get("two_year_mean_citedness")

    def close(self):
        """Release nothing.

        The stores this reads are owned by the thread, not by this object,
        and other callers on the same thread share them. Closing here would
        pull a connection out from under them. Use
        :func:`crossref_local._core.store.close_stores` to release a
        thread's stores.
        """

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ---------------------------------------------------------------------------
# ISSN -> impact-factor proxy, indexed once
# ---------------------------------------------------------------------------
# The HTTP server and the CLI both annotate search results with a journal's
# IF proxy, and both used to run one lookup per ISSN. With no filtered read
# that would be one full scan per ISSN, so the mapping is built in a single
# pass and kept. It is a cache with the same staleness the per-ISSN caches
# had before: a journal record written after the first lookup is not seen
# until the process restarts.

_IF_INDEX: Optional[Dict[str, Optional[float]]] = None


def impact_factor_index(store=None) -> Dict[str, Optional[float]]:
    """Map every known ISSN to its journal's 2-year mean citedness.

    Args:
        store: The journal collection. When given, a fresh index is built
            and NOT cached — a caller that passes its own store is asking
            about that store, and caching it would answer a later default
            call with the wrong collection.
    """
    global _IF_INDEX

    if store is None and _IF_INDEX is not None:
        return _IF_INDEX

    index: Dict[str, Optional[float]] = {}
    source = store if store is not None else journals_store()
    for row in source.rows():
        values = row.values
        proxy = values.get("two_year_mean_citedness")
        for issn in _issns_of(values):
            index.setdefault(issn, proxy)

    if store is None:
        _IF_INDEX = index
    return index


def impact_factor_for_issn(issn: str, store=None) -> Optional[float]:
    """The IF proxy for one ISSN, or None when unknown.

    Exact ISSN matching. The previous implementations compared the ISSN
    against the serialised ``issns`` text with a wildcard, which also
    matched a journal that merely contained the ISSN as a substring.
    """
    if not issn:
        return None
    try:
        return impact_factor_index(store).get(issn)
    except Exception:
        # An unreachable or unpopulated journal collection means "unknown
        # impact factor", not a failed search — the caller is annotating
        # results it already has.
        return None

# EOF
