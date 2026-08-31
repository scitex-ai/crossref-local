"""
Impact Factor calculation module.

Calculates journal impact factors from the local CrossRef corpus by
analyzing citation patterns.

Usage:
    >>> from crossref_local._impact_factor import ImpactFactorCalculator
    >>> with ImpactFactorCalculator() as calc:
    ...     result = calc.calculate_impact_factor("Nature", target_year=2023)
    ...     print(f"IF: {result['impact_factor']:.3f}")
"""

from .calculator import ImpactFactorCalculator
from .journal_lookup import (
    JournalLookup,
    impact_factor_for_issn,
    impact_factor_index,
)

__all__ = [
    "ImpactFactorCalculator",
    "JournalLookup",
    "impact_factor_for_issn",
    "impact_factor_index",
]

# EOF
