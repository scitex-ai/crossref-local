#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Impact Factor Calculator from CrossRef Local Database

Calculates journal impact factors by analyzing citation patterns
in the local CrossRef database.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import scitex_logging as slogging

from .journal_lookup import JournalLookup
from ..config import Config

logger = slogging.getLogger(__name__)


class ImpactFactorCalculator:
    """
    Calculate journal impact factors from local CrossRef database.

    Supports:
    - 2-year and 5-year impact factors
    - Moving averages
    - Multiple calculation methods
    - Journal identification by name or ISSN
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize calculator with database connection.

        Args:
            db_path: Path to CrossRef SQLite database. Auto-detects if None.
        """
        if db_path is None:
            self.db_path = Config.get_db_path()
        else:
            self.db_path = Path(db_path)
            if not self.db_path.exists():
                raise FileNotFoundError(f"Database not found: {db_path}")

        self._journal_lookup = JournalLookup(str(self.db_path))

    def _get_connection(self):
        """Create a new database connection (context manager).

        Creates a fresh connection for each query to ensure thread safety.
        SQLite connections cannot be shared across threads.
        """
        from contextlib import contextmanager

        @contextmanager
        def connection():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

        return connection()

    def close(self):
        """Close resources (no-op, connections are per-query now)."""
        if self._journal_lookup:
            self._journal_lookup.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_journal_issn(self, journal_name: str) -> Optional[str]:
        """
        Get ISSN for a journal name.

        Uses the journals lookup table for fast resolution.
        Falls back to slow query if table doesn't exist.

        Args:
            journal_name: Journal name (e.g., "Nature")

        Returns:
            ISSN string or None
        """
        return self._journal_lookup.get_issn(journal_name)

    def get_article_dois(
        self,
        journal_identifier: str,
        year: int,
        use_issn: bool = False,
        citable_only: bool = True
    ) -> List[str]:
        """
        Get DOIs for articles in a journal for a specific year.

        Optimized: only fetches DOIs, not full metadata.

        Args:
            journal_identifier: Journal name or ISSN
            year: Publication year
            use_issn: If True, search by ISSN instead of name
            citable_only: If True, only return citable items (>20 references)
                         This matches JCR's definition of citable items.

        Returns:
            List of DOI strings
        """
        # Citable items filter: research articles typically have >20 references
        # This excludes news, editorials, letters, corrections, etc.
        citable_filter = "AND json_array_length(json_extract(metadata, '$.reference')) > 20" if citable_only else ""

        if use_issn:
            query = f"""
            SELECT doi
            FROM works
            WHERE json_extract(metadata, '$.ISSN[0]') = ?
            AND json_extract(metadata, '$.published.date-parts[0][0]') = ?
            AND type = 'journal-article'
            {citable_filter}
            """
            params = (journal_identifier, year)
        else:
            query = f"""
            SELECT doi
            FROM works
            WHERE json_extract(metadata, '$.container-title[0]') LIKE ?
            AND json_extract(metadata, '$.published.date-parts[0][0]') = ?
            AND type = 'journal-article'
            {citable_filter}
            """
            params = (f"%{journal_identifier}%", year)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [row[0] for row in cursor]

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
        if use_issn:
            query = """
            SELECT COUNT(*) as count
            FROM works
            WHERE json_extract(metadata, '$.ISSN[0]') = ?
            AND json_extract(metadata, '$.published.date-parts[0][0]') = ?
            AND type = 'journal-article'
            """
            params = (journal_identifier, year)
        else:
            query = """
            SELECT COUNT(*) as count
            FROM works
            WHERE json_extract(metadata, '$.container-title[0]') LIKE ?
            AND json_extract(metadata, '$.published.date-parts[0][0]') = ?
            AND type = 'journal-article'
            """
            params = (f"%{journal_identifier}%", year)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result else 0

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
            method: "citations-table" (fast, year-specific),
                    "is-referenced-by" (fast, cumulative),
                    "reference-graph" (slow, accurate)

        Returns:
            Total citation count
        """
        if method == "citations-table":
            return self._count_citations_from_table(dois, citation_year)
        elif method == "is-referenced-by":
            return self._count_citations_simple(dois, citation_year)
        else:
            return self._count_citations_from_graph(dois, citation_year)

    def _count_citations_from_table(self, dois: List[str], citation_year: int) -> int:
        """
        Fast citation count using citations table with indexed lookup.

        Uses idx_citations_cited_new (cited_doi, citing_year) index.
        """
        if not dois:
            return 0

        # Batch query for efficiency
        placeholders = ','.join('?' * len(dois))
        query = f"""
        SELECT COUNT(*) as total
        FROM citations
        WHERE cited_doi IN ({placeholders})
        AND citing_year = ?
        """

        params = dois + [citation_year]
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result and result[0] else 0

    def _count_citations_simple(self, dois: List[str], citation_year: int) -> int:
        """
        Use is-referenced-by-count field (current citations only).

        Note: This gives current total citations, not year-specific.
        For accurate year-by-year IF, use reference-graph method.
        """
        if not dois:
            return 0

        # Create placeholders for DOIs
        placeholders = ','.join('?' * len(dois))
        query = f"""
        SELECT SUM(CAST(json_extract(metadata, '$.is-referenced-by-count') AS INTEGER)) as total
        FROM works
        WHERE doi IN ({placeholders})
        """

        with self._get_connection() as conn:
            cursor = conn.execute(query, dois)
            result = cursor.fetchone()
            return result[0] if result and result[0] else 0

    def _count_citations_from_graph(self, dois: List[str], citation_year: int) -> int:
        """
        Count citations by building citation graph from reference fields.

        This is more accurate as it respects citation year.
        """
        if not dois:
            return 0

        # Create a set for fast lookup
        target_dois = set(doi.lower() for doi in dois)
        citation_count = 0

        # Query articles published in citation_year
        logger.info(f"  Querying articles with references published in {citation_year}...")
        query = """
        SELECT metadata
        FROM works
        WHERE json_extract(metadata, '$.published.date-parts[0][0]') = ?
        AND json_extract(metadata, '$.reference') IS NOT NULL
        """

        with self._get_connection() as conn:
            cursor = conn.execute(query, (citation_year,))

            articles_checked = 0
            for row in cursor:
                articles_checked += 1
                if articles_checked % 1000 == 0:
                    logger.info(f"  Checked {articles_checked} articles, found {citation_count} citations so far...")

                metadata = json.loads(row['metadata'])
                references = metadata.get('reference', [])

                # Check if any reference DOI matches our target DOIs
                for ref in references:
                    ref_doi = ref.get('DOI', '').lower()
                    if ref_doi in target_dois:
                        citation_count += 1

            logger.info(f"  Checked {articles_checked} total articles with references")
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
            method: "citations-table" (fast), "is-referenced-by", or "reference-graph"
            citable_only: If True, only count citable items (research articles with >20 refs)
                         This matches JCR methodology. Default True.

        Returns:
            Dictionary with calculation results
        """
        logger.info(f"Calculating {window_years}-year IF for {journal_identifier} in {target_year}")

        # If journal name provided, convert to ISSN for faster queries
        if not use_issn:
            logger.info(f"Looking up ISSN for journal: {journal_identifier}")
            issn = self.get_journal_issn(journal_identifier)
            if issn:
                logger.info(f"Found ISSN: {issn} - using for faster queries")
                journal_identifier = issn
                use_issn = True
            else:
                logger.warning(f"Could not find ISSN for {journal_identifier}, using journal name (slower)")

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
        try:
            import numpy as np
        except ImportError:
            np = None

        # Extract IF values
        if_values = [r['impact_factor'] for r in if_time_series]

        # Calculate moving average (numpy when available, else pure python)
        if len(if_values) >= window:
            if np is not None:
                ma_values = np.convolve(if_values, np.ones(window)/window, mode='valid')

                # Pad with None for years where MA can't be calculated
                padding = [None] * (window - 1)
                ma_values = padding + list(ma_values)
            else:
                ma_values = [None] * (window - 1) + [
                    sum(if_values[i:i + window]) / window
                    for i in range(len(if_values) - window + 1)
                ]
        else:
            ma_values = [None] * len(if_values)

        # Add to results
        for result, ma_value in zip(if_time_series, ma_values):
            result['moving_average'] = ma_value

        return if_time_series


if __name__ == "__main__":
    # Example usage
    import click

    with ImpactFactorCalculator() as calc:
        # Test: Calculate IF for Nature in 2023
        result = calc.calculate_impact_factor(
            journal_identifier="Nature",
            target_year=2023,
            window_years=2,
            method="is-referenced-by"
        )

        click.echo("\n" + "="*60)
        click.echo(f"Journal: {result['journal']}")
        click.echo(f"Target Year: {result['target_year']}")
        click.echo(f"Window: {result['window_range']}")
        click.echo(f"Articles: {result['total_articles']}")
        click.echo(f"Citations: {result['total_citations']}")
        click.echo(f"Impact Factor: {result['impact_factor']:.3f}")
        click.echo("="*60)

# EOF
