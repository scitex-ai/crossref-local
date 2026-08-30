"""Tests for crossref_local._core.fts (query grammar over the works store).

Self-provisioning: a small, deliberately-shaped corpus is written into a
throwaway schema by the ``seeded_works`` fixture, so every assertion below
is about a KNOWN population rather than about whatever the production
corpus happens to contain. That is what makes exact counts assertable at
all — the old file could only ask "is this an int, is it non-negative".

WHAT WAS DROPPED. ``test_works_fts_virtual_table_exists_in_schema`` asked a
system catalog whether a companion full-text table existed. There is no such
table and no catalog to ask: searchable text is now three ordinary fields on
the work itself, written in the same upsert as the rest of the record. The
property it was really protecting — a stored work is findable — is covered
here (every seeded DOI is reachable by a query) and in ``test_cli_update``
(an upserted work is findable immediately afterwards).
"""

import pytest

from crossref_local._core.fts import (
    _count_with_store,
    _search_with_store,
    count,
    matches,
    search,
    search_dois,
)
from crossref_local._core.models import SearchResult, Work
from crossref_local._core.store import works_store

# ---------------------------------------------------------------------------
# The corpus. Every record carries the word "study", so a query for it
# returns all eight in DOI order — which is what makes the paging assertions
# exact. The remaining vocabulary is placed so each operator has both a
# match and a non-match to separate:
#
#   "machine learning" (phrase)  -> 001 only   (002 says "learning machine")
#   machine                      -> 001, 002
#   learning                     -> 001, 002
#   cortical                     -> 001, 003, 006
#   sleep                        -> 003, 006
#   hippocampal                  -> 005, 006
#   quantum                      -> 004, 008
#   protein                      -> 002, 007
# ---------------------------------------------------------------------------
_SEED = (
    (
        "10.1000/fts.001",
        "Machine learning for spike sorting",
        "A study of deep networks applied to cortical recordings.",
        "Ada Lovelace",
        "Journal of Neural Engineering",
    ),
    (
        "10.1000/fts.002",
        "A learning machine for protein folding",
        "A study predicting folding from sequence alone.",
        "Grace Hopper",
        "Protein Science",
    ),
    (
        "10.1000/fts.003",
        "Cortical oscillations during sleep",
        "A study of ripples and spindles in the hippocampus.",
        "Rosalind Franklin",
        "Journal of Neurophysiology",
    ),
    (
        "10.1000/fts.004",
        "Quantum coherence in photosynthesis",
        "A study of excitons and vibrational modes.",
        "Marie Curie",
        "Nature Physics",
    ),
    (
        "10.1000/fts.005",
        "HIPPOCAMPAL replay in navigation",
        "A study of place cells encoding trajectories.",
        "Alan Turing",
        "Neuron",
    ),
    (
        "10.1000/fts.006",
        "Memory consolidation during sleep",
        "A study of the cortical to hippocampal dialogue.",
        "Barbara McClintock",
        "Nature Neuroscience",
    ),
    (
        "10.1000/fts.007",
        "Protein structure prediction",
        "A study of folding energetics.",
        "Dorothy Hodgkin",
        "Structural Biology",
    ),
    (
        "10.1000/fts.008",
        "Spectroscopy of quantum dots",
        "A study of optical emission properties.",
        "Lise Meitner",
        "Applied Optics",
    ),
)

#: Every seeded DOI, in the order ``matches()`` promises to return them.
_ALL_DOIS = tuple(sorted(row[0] for row in _SEED))

#: A term carried by every record.
_EVERY = "study"


@pytest.fixture
def seeded_works(store_env):
    """Write the shaped corpus into a throwaway store."""
    from scitex_dev.store import NEW_RECORD

    store = works_store()
    for doi, title, abstract, authors, container in _SEED:
        store.put(
            {
                "doi": doi,
                "metadata": {"DOI": doi, "title": [title]},
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "container_title": container,
                "year": 2024,
            },
            expected_revision=NEW_RECORD,
        )
    return store


# ---------- result shape ----------


def test_search_returns_a_search_result(seeded_works):
    # Arrange
    # Act
    results = search(_EVERY, limit=1)
    # Assert
    assert isinstance(results, SearchResult)


def test_search_echoes_the_supplied_query(seeded_works):
    # Arrange
    query = "cortical"
    # Act
    results = search(query, limit=1)
    # Assert
    assert results.query == query


def test_search_total_is_an_integer(seeded_works):
    # Arrange
    # Act
    results = search(_EVERY, limit=1)
    # Assert
    assert isinstance(results.total, int)


def test_search_reports_the_full_match_count_not_the_page_size(seeded_works):
    # Arrange
    # Act
    results = search(_EVERY, limit=2)
    # Assert
    assert results.total == len(_SEED)


def test_search_elapsed_ms_is_a_float(seeded_works):
    # Arrange
    # Act
    results = search(_EVERY, limit=1)
    # Assert
    assert isinstance(results.elapsed_ms, float)


def test_search_elapsed_ms_is_nonnegative(seeded_works):
    # Arrange
    # Act
    results = search(_EVERY, limit=1)
    # Assert
    assert results.elapsed_ms >= 0


def test_search_returns_work_objects(seeded_works):
    # Arrange
    # Act
    results = search(_EVERY, limit=3)
    # Assert
    assert all(isinstance(work, Work) for work in results.works)


def test_search_respects_the_limit_argument(seeded_works):
    # Arrange
    limit = 3
    # Act
    results = search(_EVERY, limit=limit)
    # Assert
    assert len(results.works) == limit


# ---------- the query grammar ----------


def test_bare_term_matches_every_record_carrying_it(seeded_works):
    # Arrange
    # Act
    total = count("machine")
    # Assert
    assert total == 2


def test_quoted_phrase_requires_the_words_adjacent(seeded_works):
    # Arrange — 002 carries both words as "learning machine", which the
    # phrase must NOT match.
    # Act
    dois = search_dois('"machine learning"')
    # Assert
    assert dois == ["10.1000/fts.001"]


def test_adjacent_terms_are_joined_by_and(seeded_works):
    # Arrange
    # Act
    total = count("machine learning")
    # Assert
    assert total == 2


def test_explicit_and_requires_both_terms(seeded_works):
    # Arrange
    # Act
    total = count("cortical AND sleep")
    # Assert
    assert total == 2


def test_or_unions_the_alternatives(seeded_works):
    # Arrange — quantum is 004/008, sleep is 003/006.
    # Act
    total = count("quantum OR sleep")
    # Assert
    assert total == 4


def test_not_excludes_the_term_that_follows_it(seeded_works):
    # Arrange — cortical is 001/003/006; sleep removes 003 and 006.
    # Act
    dois = search_dois("cortical NOT sleep")
    # Assert
    assert dois == ["10.1000/fts.001"]


def test_near_is_accepted_and_behaves_as_and(seeded_works):
    # Arrange — proximity needs positional data this store does not keep,
    # so NEAR widens to AND rather than returning ordered nonsense.
    # Act
    total = count("machine NEAR learning")
    # Assert
    assert total == count("machine AND learning")


def test_matching_is_case_insensitive(seeded_works):
    # Arrange — 005 stores the term upper-case, 006 lower-case.
    # Act
    total = count("hippocampal")
    # Assert
    assert total == 2


def test_an_upper_case_query_matches_a_lower_case_record(seeded_works):
    # Arrange
    # Act
    total = count("HiPpOcAmPaL")
    # Assert
    assert total == 2


def test_the_container_title_is_searchable(seeded_works):
    # Arrange — only 004 is published in Nature Physics.
    # Act
    dois = search_dois('"nature physics"')
    # Assert
    assert dois == ["10.1000/fts.004"]


def test_the_author_list_is_searchable(seeded_works):
    # Arrange
    # Act
    dois = search_dois("meitner")
    # Assert
    assert dois == ["10.1000/fts.008"]


def test_an_empty_query_matches_nothing(seeded_works):
    # Arrange — returning everything would turn a caller's missing input
    # into a full-corpus read.
    # Act
    total = count("")
    # Assert
    assert total == 0


def test_a_whitespace_only_query_matches_nothing(seeded_works):
    # Arrange
    # Act
    total = count("   ")
    # Assert
    assert total == 0


def test_a_term_present_in_no_record_matches_nothing(seeded_works):
    # Arrange
    # Act
    total = count("xyzzy12345nonexistent")
    # Assert
    assert total == 0


# ---------- count() agrees with search() ----------


def test_count_agrees_with_search_total(seeded_works):
    # Arrange
    query = "cortical OR quantum"
    # Act
    total = search(query, limit=1).total
    # Assert
    assert count(query) == total


def test_count_agrees_with_search_total_for_a_phrase(seeded_works):
    # Arrange
    query = '"machine learning"'
    # Act
    total = search(query, limit=1).total
    # Assert
    assert count(query) == total


# ---------- search_dois() ----------


def test_search_dois_returns_a_list(seeded_works):
    # Arrange
    # Act
    dois = search_dois(_EVERY)
    # Assert
    assert isinstance(dois, list)


def test_search_dois_returns_only_strings(seeded_works):
    # Arrange
    # Act
    dois = search_dois(_EVERY)
    # Assert
    assert all(isinstance(doi, str) for doi in dois)


def test_search_dois_returns_only_doi_shaped_strings(seeded_works):
    # Arrange
    # Act
    dois = search_dois(_EVERY)
    # Assert
    assert all(doi.startswith("10.") for doi in dois)


def test_search_dois_respects_the_limit_argument(seeded_works):
    # Arrange
    # Act
    dois = search_dois(_EVERY, limit=3)
    # Assert
    assert len(dois) == 3


# ---------- paging is stable, and ordered by DOI ----------


def test_matches_are_returned_in_doi_order(seeded_works):
    # Arrange — the ordering is imposed by this module, not by the store,
    # precisely so an offset means the same thing on every call.
    # Act
    dois = search_dois(_EVERY)
    # Assert
    assert dois == list(_ALL_DOIS)


@pytest.fixture
def two_pages(seeded_works):
    """Two consecutive pages of the same query."""
    first = search(_EVERY, limit=3, offset=0)
    second = search(_EVERY, limit=3, offset=3)
    return first, second


def test_the_first_page_holds_the_first_dois_in_order(two_pages):
    # Arrange
    first, _second = two_pages
    # Act
    dois = [work.doi for work in first.works]
    # Assert
    assert dois == list(_ALL_DOIS[:3])


def test_the_second_page_continues_where_the_first_stopped(two_pages):
    # Arrange
    _first, second = two_pages
    # Act
    dois = [work.doi for work in second.works]
    # Assert
    assert dois == list(_ALL_DOIS[3:6])


def test_the_two_pages_share_no_work(two_pages):
    # Arrange
    first, second = two_pages
    # Act
    overlap = {w.doi for w in first.works} & {w.doi for w in second.works}
    # Assert
    assert overlap == set()


def test_both_pages_report_the_same_total(two_pages):
    # Arrange
    first, second = two_pages
    # Act
    # Assert
    assert first.total == second.total


def test_an_offset_past_the_end_returns_an_empty_page(seeded_works):
    # Arrange
    # Act
    results = search(_EVERY, limit=3, offset=len(_SEED) + 1)
    # Assert
    assert results.works == []


def test_search_reports_that_a_page_was_capped(seeded_works):
    # Arrange
    # Act
    results = search(_EVERY, limit=2)
    # Assert
    assert results.limit_info.capped is True


# ---------- matches() and the explicit-store helpers ----------


def test_matches_returns_store_rows(seeded_works):
    # Arrange
    # Act
    hits = matches("quantum")
    # Assert
    assert [str(row.values["doi"]) for row in hits] == [
        "10.1000/fts.004",
        "10.1000/fts.008",
    ]


def test_search_with_an_explicit_store_returns_the_same_total(seeded_works):
    # Arrange — the async layer runs this on a worker thread with that
    # thread's own store.
    # Act
    results = _search_with_store(seeded_works, "quantum", 10, 0)
    # Assert
    assert results.total == 2


def test_count_with_an_explicit_store_returns_the_same_count(seeded_works):
    # Arrange
    # Act
    total = _count_with_store(seeded_works, "quantum")
    # Assert
    assert total == 2

# EOF
