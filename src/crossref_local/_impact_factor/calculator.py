#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Impact Factor Calculator over the local CrossRef corpus.

HOW THE QUERIES CHANGED, AND WHY THE FILTERS DID NOT
----------------------------------------------------
Every selection here used to be a JSON path evaluated inside the engine —
``$.ISSN[0]``, ``$.published.date-parts[0][0]``, ``$.type``, and the length
of ``$.reference``. Those four values are now denormalised onto the work
record as ``issn`` / ``year`` / ``work_type`` / ``reference_count`` by the
ingest path, so the *predicates* are unchanged; only where they are
evaluated moved, from the engine to this process.

The store primitive offers no filtered read, no aggregate and no ``IN``,
so a scan here reads the whole collection. Every method below that is not
a point read on a DOI is O(collection). That is a real regression in cost
against the previous file-backed engine and it is not hidden behind a
"fast"/"slow" label: see ``docs/adr/0001-corpus-moves-to-the-shared-store.md``.
"""

import logging
from typing import Dict, List, Optional

from .._core.store import citations_store, works_store
from .journal_lookup import JournalLookup

logger = logging.getLogger(__name__)

#: JCR counts research articles; the corpus also holds news, editorials,
#: letters and corrections. The reference-list length is the same proxy the
#: previous implementation used, kept so the numbers stay comparable.
CITABLE_MIN_REFERENCES = 20

_JOURNAL_ARTICLE = "journal-article"


def _as_int(value) -> Optional[int]:
    """An integer field as an int, or None when it is absent/unusable."""
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


class ImpactFactorCalculator:
    """
    Calculate journal impact factors from the local CrossRef corpus.

    Supports:
    - 2-year and 5-year impact factors
    - Moving averages
    - Multiple calculation methods
    - Journal identification by name or ISSN
    """

    def __init__(self, store=None, *, citations=None, journals=None):
        """
        Initialize the calculator.

        Thread-safe by construction when no store is passed: the openers in
        :mod:`crossref_local._core.store` hand out one store per thread, so
        two threads never share a connection.

        Args:
            store: The works collection (opens this thread's if not given).
            citations: The citation-edge collection (likewise).
            journals: The journal collection, used for name->ISSN
                resolution (likewise).
        """
        self._store = store
        self._citations = citations
        self._journal_lookup = JournalLookup(journals, works=store)

    def _works(self):
        return self._store if self._store is not None else works_store()

    def _citation_edges(self):
        return self._citations if self._citations is not None else citations_store()

    def close(self):
        """Release nothing.

        The stores are owned by the thread, not by this object; see
        :meth:`JournalLookup.close`. Use
        :func:`crossref_local._core.store.close_stores` to release them.
        """
        if self._journal_lookup:
            self._journal_lookup.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_journal_issn(self, journal_name: str) -> Optional[str]:
        """
        Get ISSN for a journal name.

        Resolves through the journal collection, which falls back to a
        works scan when that collection has never been populated.

        Args:
            journal_name: Journal name (e.g., "Nature")

        Returns:
            ISSN string or None
        """
        return self._journal_lookup.get_issn(journal_name)

    def _matches_journal(
        self, values, journal_identifier: str, use_issn: bool
    ) -> bool:
        """Whether one work belongs to the journal being measured.

        By ISSN the test is equality, as the previous ``=`` was. By name it
        is a case-insensitive substring, as the previous ``LIKE '%name%'``
        was — a journal name given by a caller is rarely the exact
        container title CrossRef deposited.
        """
        if use_issn:
            return values.get("issn") == journal_identifier
        container = values.get("container_title") or ""
        return journal_identifier.lower() in container.lower()

    def get_article_dois(
        self,
        journal_identifier: str,
        year: int,
        use_issn: bool = False,
        citable_only: bool = True
    ) -> List[str]:
        """
        Get DOIs for articles in a journal for a specific year.

        Args:
            journal_identifier: Journal name or ISSN
            year: Publication year
            use_issn: If True, search by ISSN instead of name
            citable_only: If True, only return citable items (>20
                references). This matches JCR's definition of citable items.

        Returns:
            List of DOI strings
        """
        dois: List[str] = []
        for row in self._works().rows():
            values = row.values
            if values.get("work_type") != _JOURNAL_ARTICLE:
                continue
            if _as_int(values.get("year")) != year:
                continue
            if not self._matches_journal(values, journal_identifier, use_issn):
                continue
            if citable_only:
                references = _as_int(values.get("reference_count")) or 0
                if references <= CITABLE_MIN_REFERENCES:
                    continue
            doi = values.get("doi")
            if doi:
                dois.append(str(doi))
        return dois

    def count_articles(
        self,
        journal_identifier: str,
        year: int,
        use_issn: bool = False
    ) -> int:
        """
        Count articles for a journal in a specific year.

        Args:
            journal_identifier: Journal name or ISSN
            year: Publication year
            use_issn: If True, search by ISSN

        Returns:
            Number of articles
        """
        return len(
            self.get_article_dois(
                journal_identifier, year, use_issn, citable_only=False
            )
        )

    def get_citations_to_articles(
        self,
        dois: List[str],
        citation_year: int,
        method: str = "citations-table"
    ) -> int:
        """
        Count citations to a list of DOIs in a specific year.

        Args:
            dois: List of DOIs to check citations for
            citation_year: Year when citations occurred
            method: "citations-table" (year-specific),
                    "is-referenced-by" (cumulative, point reads),
                    "reference-graph" (slowest, accurate)

        Returns:
            Total citation count
        """
        if method == "citations-table":
            return self._count_citations_from_edges(dois, citation_year)
        elif method == "is-referenced-by":
            return self._count_citations_simple(dois, citation_year)
        else:
            return self._count_citations_from_graph(dois, citation_year)

    def _count_citations_from_edges(
        self, dois: List[str], citation_year: int
    ) -> int:
        """
        Count citations from the citation-edge collection.

        Reads every edge: the store cannot answer ``cited_doi IN (...) AND
        citing_year = ?`` for us, so the membership test happens here
        against a set.
        """
        if not dois:
            return 0

        targets = set(dois)
        total = 0
        for row in self._citation_edges().rows():
            values = row.values
            if values.get("cited_doi") in targets and (
                _as_int(values.get("citing_year")) == citation_year
            ):
                total += 1
        return total

    #: The name callers already know, kept as an alias.
    _count_citations_from_table = _count_citations_from_edges

    def _count_citations_simple(self, dois: List[str], citation_year: int) -> int:
        """
        Sum the ``referenced_by_count`` of each work (current citations).

        Point reads, one per DOI — the cheapest of the three methods and
        the only one that does not scan.

        Note: This gives current total citations, not year-specific.
        For accurate year-by-year IF, use reference-graph method.
        """
        if not dois:
            return 0

        works = self._works()
        total = 0
        for doi in dois:
            row = works.get({"doi": doi})
            if row is None:
                continue
            total += _as_int(row.values.get("referenced_by_count")) or 0
        return total

    def _count_citations_from_graph(self, dois: List[str], citation_year: int) -> int:
        """
        Count citations by reading the reference list of every work
        published in ``citation_year``.

        More accurate than the cumulative count because it respects the
        citation year, and the most expensive: it reads every work.
        """
        if not dois:
            return 0

        target_dois = set(doi.lower() for doi in dois)
        citation_count = 0

        logger.info(
            "  Reading articles with references published in %s...", citation_year
        )

        articles_checked = 0
        for row in self._works().rows():
            values = row.values
            if _as_int(values.get("year")) != citation_year:
                continue

            # ``metadata`` is a declared JSON field: the primitive returns
            # a dict. Nothing is parsed here.
            metadata = values.get("metadata") or {}
            references = metadata.get("reference")
            if not references:
                continue

            articles_checked += 1
            if articles_checked % 1000 == 0:
                logger.info(
                    "  Checked %s articles, found %s citations so far...",
                    articles_checked,
                    citation_count,
                )

            for ref in references:
                if not isinstance(ref, dict):
                    continue
                if (ref.get("DOI") or "").lower() in target_dois:
                    citation_count += 1

        logger.info("  Checked %s total articles with references", articles_checked)
        return citation_count

    def calculate_impact_factor(
        self,
        journal_identifier: str,
        target_year: int,
        window_years: int = 2,
        use_issn: bool = False,
        method: str = "citations-table",
        citable_only: bool = True
    ) -> Dict:
        """
        Calculate impact factor for a journal.

        Args:
            journal_identifier: Journal name or ISSN
            target_year: Year for which to calculate IF
            window_years: Citation window (2 for 2-year IF, 5 for 5-year IF)
            use_issn: Use ISSN for journal identification
            method: "citations-table", "is-referenced-by", or
                "reference-graph"
            citable_only: If True, only count citable items (research
                articles with >20 refs). This matches JCR methodology.

        Returns:
            Dictionary with calculation results
        """
        logger.info(f"Calculating {window_years}-year IF for {journal_identifier} in {target_year}")

        # If a journal name was given, convert it to an ISSN: the ISSN test
        # is equality against a denormalised field, the name test is a
        # substring over the container title.
        if not use_issn:
            logger.info(f"Looking up ISSN for journal: {journal_identifier}")
            issn = self.get_journal_issn(journal_identifier)
            if issn:
                logger.info(f"Found ISSN: {issn} - using for exact matching")
                journal_identifier = issn
                use_issn = True
            else:
                logger.warning(f"Could not find ISSN for {journal_identifier}, using journal name")

        # Get articles published in the window years
        window_start = target_year - window_years
        window_end = target_year - 1

        logger.info(f"Fetching DOIs from {window_start} to {window_end}...")
        all_dois = []
        articles_by_year = {}

        for year in range(window_start, window_end + 1):
            dois = self.get_article_dois(journal_identifier, year, use_issn, citable_only)
            articles_by_year[year] = len(dois)
            all_dois.extend(dois)
            logger.info(f"  {year}: {len(dois)} {'citable items' if citable_only else 'articles'}")

        total_articles = len(all_dois)
        logger.info(f"Total articles in window: {total_articles}")

        if total_articles == 0:
            logger.warning(f"No articles found for {journal_identifier} in {window_start}-{window_end}")
            return {
                'journal': journal_identifier,
                'target_year': target_year,
                'window_years': window_years,
                'window_range': f"{window_start}-{window_end}",
                'articles_by_year': articles_by_year,
                'total_articles': 0,
                'total_citations': 0,
                'impact_factor': 0.0,
                'method': method,
                'status': 'no_articles'
            }

        # Count citations to these articles in target_year
        logger.info(f"Counting citations to {total_articles} articles in {target_year} (method: {method})...")
        total_citations = self.get_citations_to_articles(
            all_dois, target_year, method
        )
        logger.info(f"Found {total_citations} citations")

        # Calculate IF
        impact_factor = total_citations / total_articles if total_articles > 0 else 0.0

        logger.info(f"IF = {total_citations} / {total_articles} = {impact_factor:.3f}")

        return {
            'journal': journal_identifier,
            'target_year': target_year,
            'window_years': window_years,
            'window_range': f"{window_start}-{window_end}",
            'articles_by_year': articles_by_year,
            'total_articles': total_articles,
            'total_citations': total_citations,
            'impact_factor': impact_factor,
            'method': method,
            'citable_only': citable_only,
            'status': 'success'
        }

    def calculate_if_time_series(
        self,
        journal_identifier: str,
        start_year: int,
        end_year: int,
        window_years: int = 2,
        use_issn: bool = False,
        method: str = "is-referenced-by"
    ) -> List[Dict]:
        """
        Calculate impact factor time series.

        Args:
            journal_identifier: Journal name or ISSN
            start_year: First year to calculate
            end_year: Last year to calculate
            window_years: Citation window
            use_issn: Use ISSN for identification
            method: Citation counting method

        Returns:
            List of IF calculation results by year
        """
        results = []

        for year in range(start_year, end_year + 1):
            result = self.calculate_impact_factor(
                journal_identifier,
                year,
                window_years,
                use_issn,
                method
            )
            results.append(result)

        return results

    def calculate_moving_average(
        self,
        if_time_series: List[Dict],
        window: int = 3
    ) -> List[Dict]:
        """
        Calculate moving average of impact factors.

        Args:
            if_time_series: List of IF results from calculate_if_time_series
            window: Moving average window size

        Returns:
            List with added moving_average field
        """
        import numpy as np

        # Extract IF values
        if_values = [r['impact_factor'] for r in if_time_series]

        # Calculate moving average
        if len(if_values) >= window:
            ma_values = np.convolve(if_values, np.ones(window)/window, mode='valid')

            # Pad with None for years where MA can't be calculated
            padding = [None] * (window - 1)
            ma_values = padding + list(ma_values)
        else:
            ma_values = [None] * len(if_values)

        # Add to results
        for result, ma_value in zip(if_time_series, ma_values):
            result['moving_average'] = ma_value

        return if_time_series


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    with ImpactFactorCalculator() as calc:
        result = calc.calculate_impact_factor(
            journal_identifier="Nature",
            target_year=2023,
            window_years=2,
            method="is-referenced-by"
        )

        print("\n" + "="*60)
        print(f"Journal: {result['journal']}")
        print(f"Target Year: {result['target_year']}")
        print(f"Window: {result['window_range']}")
        print(f"Articles: {result['total_articles']}")
        print(f"Citations: {result['total_citations']}")
        print(f"Impact Factor: {result['impact_factor']:.3f}")
        print("="*60)

# EOF
