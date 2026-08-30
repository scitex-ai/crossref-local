#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: "2026-01-07 22:45:01 (ywatanabe)"
# File: examples/03_impact_factor/00_calculate_impact_factor.py


"""
Demo: Impact Factor Calculation

Example usage of the CrossRef Local impact factor calculator.
Compares calculated IF with OpenAlex IF proxy.

Usage:
    ./00_calculate_impact_factor.py --journal Nature --year 2023
    ./00_calculate_impact_factor.py --journal Science --year 2023 --duration 5
"""

import scitex as stx

# The calculator ships with the package. It used to be imported from a
# sibling `impact_factor/` checkout via sys.path and constructed with a
# corpus file path; it now opens this thread's store itself, so there is
# neither a path to pass nor a directory to reach into.
from crossref_local._impact_factor import ImpactFactorCalculator


@stx.session
def main(
    journal: str = "Nature",
    year: int = 2023,
    duration: int = 2,
    CONFIG=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """Calculate one journal's impact factor and compare it with OpenAlex.

    Args:
        journal: Journal name (e.g. "Nature", "The Lancet")
        year: Target year for the impact factor
        duration: Citation window in years
    """
    logger.info("=" * 60)
    logger.info("  Impact Factor Calculation")
    logger.info("=" * 60)

    calc = ImpactFactorCalculator()

    # Lookup ISSN and OpenAlex IF proxy
    logger.info(f"  Looking up: {journal}")
    issn = calc.get_journal_issn(journal)
    openalex_if = calc._journal_lookup.get_if_proxy(journal)
    journal_info = calc._journal_lookup.search(journal, limit=1)

    if issn:
        logger.info(f"  ISSN: {issn}")
        identifier = issn
        use_issn = True
    else:
        logger.info("  ISSN not found, using journal name (slower)")
        identifier = journal
        use_issn = False

    if openalex_if:
        logger.info(f"  OpenAlex IF (2yr): {openalex_if:.2f}")

    if journal_info:
        info = journal_info[0]
        if info.get("h_index"):
            logger.info(f"  OpenAlex h-index: {info['h_index']}")
        if info.get("works_count"):
            logger.info(f"  OpenAlex works: {info['works_count']:,}")

    logger.info(f"  Calculating {duration}-year IF for {year}...")

    result = calc.calculate_impact_factor(
        journal_identifier=identifier,
        target_year=year,
        window_years=duration,
        use_issn=use_issn,
        # Fast, year-specific: reads the citation-edge collection.
        method="citations-table",
        # Only count citable items (research articles) per JCR methodology.
        citable_only=True,
    )

    logger.info("-" * 60)
    logger.info(f"  Journal:           {journal}")
    if issn:
        logger.info(f"  ISSN:              {issn}")
    logger.info(f"  Target Year:       {result['target_year']}")
    logger.info(f"  Window:            {result['window_range']}")
    logger.info(f"  Citable Items:     {result['total_articles']:,}")
    logger.info(f"  Citations:         {result['total_citations']:,}")
    logger.info("-" * 60)
    logger.info(f"  Calculated IF:     {result['impact_factor']:.2f}")
    if openalex_if:
        logger.info(f"  OpenAlex IF:       {openalex_if:.2f}")
    logger.info("-" * 60)

    # Show methodology note
    logger.info("  Note: Uses JCR methodology - citable items only (>20 refs)")
    logger.info("  excludes news, editorials, letters, corrections")
    logger.info("=" * 60)

    calc.close()
    return 0


if __name__ == "__main__":
    main()

# EOF
