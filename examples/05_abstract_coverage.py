#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: "2026-02-10 (ywatanabe)"
# File: /home/ywatanabe/proj/crossref-local/examples/05_abstract_coverage.py

"""Calculate abstract coverage statistics for the CrossRef Local corpus.

This script calculates:
1. Global abstract availability ratio
2. Per-type coverage (journal-article, book-chapter, etc.)
3. Per-publisher coverage (by member ID)
4. Per-year coverage

HOW IT READS, AND WHY IT IS SLOW
--------------------------------
It used to open the corpus file directly and let the engine do the work:
four aggregate queries with ``json_extract`` / ``GROUP BY`` / ``HAVING``,
each returning a handful of rows.

The corpus now lives in the shared store primitive, which has no filtered
read, no aggregate and no count. ``works_store().rows()`` returns EVERY
record, and the grouping happens here in Python. So this script reads the
whole collection exactly once and accumulates all four breakdowns in that
single pass — one pass rather than four, because each one costs the same
full read.

Be honest about what that means: on the full corpus this is a very
expensive script, not a quick stat. Nothing in this package can make it
cheaper, because the number it wants is not one the store keeps.
"""

import scitex as stx

from crossref_local._core.store import works_store


def _has_abstract(values) -> bool:
    """Whether this work carries a non-empty abstract.

    Reads the denormalised ``abstract`` field, which the ingest path writes
    from the same CrossRef ``abstract`` key the old ``json_extract(metadata,
    '$.abstract')`` expression pulled out — same source, evaluated at write
    time instead of on every row of every query.
    """
    return bool((values.get("abstract") or "").strip())


def _member_of(values):
    """The CrossRef member (publisher) id, or None.

    Not a denormalised field, so it comes out of ``metadata`` — which the
    primitive returns as a dict, no manual decode.
    """
    metadata = values.get("metadata")
    if not isinstance(metadata, dict):
        return None
    member = metadata.get("member")
    return str(member) if member not in (None, "") else None


@stx.session
def main(
    top_n: int = 20,
    CONFIG=stx.session.INJECTED,
    plt=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """Calculate abstract coverage statistics.

    Args:
        top_n: Number of top publishers to show
    """
    # =========================================================================
    # 0. The single pass
    # =========================================================================
    logger.info("=" * 70)
    logger.info("ABSTRACT COVERAGE STATISTICS (Crossref)")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Reading the whole works collection (this is the slow part).")

    total = 0
    with_abstract = 0
    by_type = {}
    by_member = {}
    by_year = {}

    def _bump(bucket, key, has_abstract):
        entry = bucket.setdefault(key, {"total": 0, "with_abstract": 0})
        entry["total"] += 1
        if has_abstract:
            entry["with_abstract"] += 1

    for row in works_store().rows():
        values = row.values
        has_abstract = _has_abstract(values)

        total += 1
        if has_abstract:
            with_abstract += 1

        work_type = values.get("work_type") or ""
        if work_type:
            _bump(by_type, work_type, has_abstract)

        member = _member_of(values)
        if member:
            _bump(by_member, member, has_abstract)

        year = values.get("year")
        if isinstance(year, int) and 2014 <= year <= 2024:
            _bump(by_year, year, has_abstract)

    if total == 0:
        logger.warning(
            "The works collection is empty. Populate it with "
            "`crossref-local update-db`, then re-run this script."
        )
        return 1

    # =========================================================================
    # 1. Global Coverage
    # =========================================================================
    ratio = (with_abstract / total) * 100

    logger.info("")
    logger.info("Global Statistics:")
    logger.info(f"  Total works: {total:,}")
    logger.info(f"  With abstract: {with_abstract:,}")
    logger.info(f"  Coverage: {ratio:.1f}%")

    # =========================================================================
    # 1b. Coverage by Work Type
    # =========================================================================
    logger.info("\n" + "-" * 70)
    logger.info("Coverage by Work Type")
    logger.info("-" * 70)
    logger.info(
        "(Note: book-review, editorial, letter, etc. often lack abstracts by design)"
    )

    def _coverage(entry):
        return (
            (entry["with_abstract"] / entry["total"]) * 100
            if entry["total"] > 0
            else 0
        )

    # Top 25 by volume, as the old `ORDER BY total DESC LIMIT 25` did.
    types = sorted(by_type.items(), key=lambda kv: -kv[1]["total"])[:25]

    logger.info(f"\n{'Work Type':<35} {'Total':>15} {'Abstract':>15} {'Coverage':>10}")
    logger.info("-" * 77)
    for work_type, entry in types:
        logger.info(
            f"{work_type:<35} {entry['total']:>15,} "
            f"{entry['with_abstract']:>15,} {_coverage(entry):>9.1f}%"
        )

    # Highlight journal-article specifically
    journal_article = by_type.get("journal-article")
    if journal_article and journal_article["total"] > 0:
        ja_coverage = _coverage(journal_article)
        logger.info(
            f"\n>>> Journal-article coverage: {ja_coverage:.1f}% "
            f"({journal_article['with_abstract']:,} / {journal_article['total']:,})"
        )

    # =========================================================================
    # 2. Per-Member/Publisher Coverage (Top N)
    # =========================================================================
    logger.info("\n" + "-" * 70)
    logger.info(f"Coverage by Publisher/Member (Top {top_n})")
    logger.info("-" * 70)

    # `HAVING total > 10000` in the old query — members below that are noise.
    members = sorted(
        (kv for kv in by_member.items() if kv[1]["total"] > 10000),
        key=lambda kv: -kv[1]["total"],
    )[:top_n]

    logger.info(f"\n{'Member ID':<15} {'Total':>15} {'Abstract':>15} {'Coverage':>10}")
    logger.info("-" * 57)
    for member, entry in members:
        logger.info(
            f"{member:<15} {entry['total']:>15,} "
            f"{entry['with_abstract']:>15,} {_coverage(entry):>9.1f}%"
        )

    # =========================================================================
    # 3. Coverage by Year
    # =========================================================================
    logger.info("\n" + "-" * 70)
    logger.info("Coverage by Publication Year (Recent 10 Years)")
    logger.info("-" * 70)

    # The old query bucketed on `created_date_time`, a column that only the
    # file-backed schema had. `year` is the publication year the ingest path
    # derives from CrossRef's own date-parts, so these numbers are keyed on
    # publication rather than deposit — which is what the heading already
    # claimed they were.
    years = sorted(by_year.items(), key=lambda kv: -kv[0])

    logger.info(f"\n{'Year':<10} {'Total':>15} {'Abstract':>15} {'Coverage':>10}")
    logger.info("-" * 52)
    for year, entry in years:
        logger.info(
            f"{year:<10} {entry['total']:>15,} "
            f"{entry['with_abstract']:>15,} {_coverage(entry):>9.1f}%"
        )

    # =========================================================================
    # 4. Summary
    # =========================================================================
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY (for documentation)")
    logger.info("=" * 70)
    logger.info(f"\nGlobal abstract coverage: {ratio:.1f}%")
    logger.info(f"Total works: {total:,}")

    # Save summary to CSV
    import pandas as pd

    # Type coverage
    type_data = [
        {
            "type": work_type,
            "total": entry["total"],
            "with_abstract": entry["with_abstract"],
            "coverage": round(_coverage(entry), 1),
        }
        for work_type, entry in types
    ]
    df_type = pd.DataFrame(type_data)
    stx.io.save(df_type, "type_coverage.csv")

    # Year coverage
    year_data = [
        {
            "year": year,
            "total": entry["total"],
            "with_abstract": entry["with_abstract"],
            "coverage": round(_coverage(entry), 1),
        }
        for year, entry in years
    ]
    df_year = pd.DataFrame(year_data)
    stx.io.save(df_year, "year_coverage.csv")

    logger.info("\nSaved: type_coverage.csv, year_coverage.csv")

    return 0


if __name__ == "__main__":
    main()

# EOF
