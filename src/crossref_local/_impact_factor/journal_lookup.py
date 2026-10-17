#!/usr/bin/env python3
"""
Journal lookup module for fast name-to-ISSN resolution.

Uses OpenAlex journals table (222k journals with IF proxy) for fast lookups.
Falls back to direct database query if table doesn't exist.
"""

import json
import sqlite3
from typing import Dict, List, Optional

import scitex_logging as slogging

logger = slogging.getLogger(__name__)


class JournalLookup:
    """
    Fast journal name to ISSN lookup.

    Uses journals_openalex table for O(1) lookups with IF proxy data.
    Falls back to slow works table scan if OpenAlex table doesn't exist.

    Thread-safe: creates a new connection for each query to avoid
    SQLite threading issues in async/multi-threaded environments.
    """

    def __init__(self, db_path: str):
        """
        Initialize journal lookup.

        Args:
            db_path: Path to CrossRef SQLite database
        """
        self.db_path = db_path
        # Check table existence once at init (safe - single query)
        with self._get_connection() as conn:
            self._openalex_exists = self._check_table_exists(conn, 'journals_openalex')
            self._issn_lookup_exists = self._check_table_exists(conn, 'issn_lookup')

        if self._openalex_exists:
            logger.info("Using journals_openalex table for fast lookups")
        else:
            logger.warning(
                "journals_openalex table not found. "
                "Run download_openalex_journals.py for fast lookups. "
                "Falling back to slow query."
            )

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

    @staticmethod
    def _check_table_exists(conn, table_name: str) -> bool:
        """Check if a table exists in the database."""
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table_name,))
        return cursor.fetchone() is not None


    def get_issn(self, journal_name: str, strict: bool = True) -> Optional[str]:
        """
        Get ISSN for a journal name.

        Args:
            journal_name: Journal name (case-insensitive)
            strict: If True, only exact matches. If False, allow partial matches.

        Returns:
            ISSN string or None if not found
        """
        if self._openalex_exists:
            return self._get_issn_openalex(journal_name, strict)
        else:
            return self._get_issn_slow(journal_name, strict)

    def _get_issn_openalex(self, journal_name: str, strict: bool = True) -> Optional[str]:
        """Fast lookup using OpenAlex journals table."""
        with self._get_connection() as conn:
            # Try exact match first
            cursor = conn.execute("""
                SELECT issn_l FROM journals_openalex
                WHERE name_lower = ?
                LIMIT 1
            """, (journal_name.lower(),))

            result = cursor.fetchone()
            if result and result[0]:
                return result[0]

            # If strict mode, don't try partial match
            if strict:
                logger.debug(f"Strict mode: no exact match for '{journal_name}'")
                return None

            # Try partial match (only if not strict)
            logger.warning(f"Using partial match for '{journal_name}' - results may be inaccurate")
            cursor = conn.execute("""
                SELECT issn_l, name FROM journals_openalex
                WHERE name_lower LIKE ?
                ORDER BY works_count DESC
                LIMIT 1
            """, (f"%{journal_name.lower()}%",))

            result = cursor.fetchone()
            if result and result[0]:
                logger.warning(f"  Matched to: '{result[1]}'")
                return result[0]
            return None

    def _get_issn_slow(self, journal_name: str, strict: bool = True) -> Optional[str]:
        """Slow lookup by scanning works table."""
        with self._get_connection() as conn:
            if strict:
                # Exact match
                cursor = conn.execute("""
                    SELECT DISTINCT json_extract(metadata, '$.ISSN[0]') as issn
                    FROM works
                    WHERE json_extract(metadata, '$.container-title[0]') = ?
                    AND json_extract(metadata, '$.ISSN[0]') IS NOT NULL
                    LIMIT 1
                """, (journal_name,))
            else:
                # Partial match
                cursor = conn.execute("""
                    SELECT DISTINCT json_extract(metadata, '$.ISSN[0]') as issn
                    FROM works
                    WHERE json_extract(metadata, '$.container-title[0]') LIKE ?
                    AND json_extract(metadata, '$.ISSN[0]') IS NOT NULL
                    LIMIT 1
                """, (f"%{journal_name}%",))

            result = cursor.fetchone()
            return result[0] if result else None

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for journals by name.

        Args:
            query: Search query (partial name match)
            limit: Maximum results to return

        Returns:
            List of journal info dictionaries with IF proxy
        """
        if not self._openalex_exists:
            return []

        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT name, issn_l, publisher, works_count,
                       two_year_mean_citedness, h_index
                FROM journals_openalex
                WHERE name_lower LIKE ?
                ORDER BY works_count DESC
                LIMIT ?
            """, (f"%{query.lower()}%", limit))

            return [
                {
                    "name": row["name"],
                    "issn": row["issn_l"],
                    "publisher": row["publisher"],
                    "works_count": row["works_count"],
                    "if_proxy": row["two_year_mean_citedness"],
                    "h_index": row["h_index"]
                }
                for row in cursor.fetchall()
            ]

    def get_info(self, issn: str) -> Optional[Dict]:
        """
        Get journal info by ISSN.

        Args:
            issn: Journal ISSN

        Returns:
            Journal info dictionary with IF proxy or None
        """
        if not self._openalex_exists:
            return None

        with self._get_connection() as conn:
            # Try direct ISSN-L match
            cursor = conn.execute("""
                SELECT name, issn_l, issns, publisher, works_count,
                       two_year_mean_citedness, h_index, is_oa
                FROM journals_openalex
                WHERE issn_l = ?
                LIMIT 1
            """, (issn,))

            row = cursor.fetchone()

            # If not found, try issn_lookup table
            if not row and self._issn_lookup_exists:
                cursor = conn.execute("""
                    SELECT jo.name, jo.issn_l, jo.issns, jo.publisher, jo.works_count,
                           jo.two_year_mean_citedness, jo.h_index, jo.is_oa
                    FROM issn_lookup il
                    JOIN journals_openalex jo ON il.journal_id = jo.id
                    WHERE il.issn = ?
                    LIMIT 1
                """, (issn,))
                row = cursor.fetchone()

            if row:
                issns = []
                if row["issns"]:
                    try:
                        issns = json.loads(row["issns"])
                    except:
                        pass
                return {
                    "name": row["name"],
                    "issn": row["issn_l"],
                    "issns": issns,
                    "publisher": row["publisher"],
                    "works_count": row["works_count"],
                    "if_proxy": row["two_year_mean_citedness"],
                    "h_index": row["h_index"],
                    "is_oa": row["is_oa"]
                }
            return None

    def get_if_proxy(self, journal_name: str, strict: bool = True) -> Optional[float]:
        """
        Get OpenAlex Impact Factor proxy for a journal.

        Args:
            journal_name: Journal name
            strict: If True, only exact matches

        Returns:
            2-year mean citedness (IF proxy) or None
        """
        if not self._openalex_exists:
            return None

        with self._get_connection() as conn:
            # Try exact match
            cursor = conn.execute("""
                SELECT two_year_mean_citedness FROM journals_openalex
                WHERE name_lower = ?
                LIMIT 1
            """, (journal_name.lower(),))

            result = cursor.fetchone()
            if result and result[0]:
                return result[0]

            if strict:
                return None

            # Try partial match (only if not strict)
            cursor = conn.execute("""
                SELECT two_year_mean_citedness FROM journals_openalex
                WHERE name_lower LIKE ?
                ORDER BY works_count DESC
                LIMIT 1
            """, (f"%{journal_name.lower()}%",))

            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def close(self):
        """Close database connection (no-op, connections are per-query now)."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
