"""Tests for crossref_local._core.stats (the exact-count cache).

Self-provisioning: every test seeds its own throwaway schema through the
``store_env`` fixture, so none of them needs the production corpus and none
of them can reach it.

WHAT WAS DROPPED AND WHY. The old file had a second family of tests around
a cheap row-id estimator — "counts_source is estimated", "MAX(rowid) still
reports the old magnitude after a DELETE", "a read-only database file still
estimates". That estimator read a file-format detail of an engine this
package no longer has, and there is no replacement path: :func:`get_counts`
now answers ``"exact"`` from the cache or ``"unavailable"``, full stop. A
test asserting a third label would be asserting a behaviour the module
deliberately refuses to have. The invariant those tests protected — the
read path never counts and never writes — is kept, and is tested harder
here than it was there.
"""

import pytest

import crossref_local
from crossref_local._core.config import Config
from crossref_local._core.stats import (
    STATS_COLLECTIONS,
    count_citations,
    count_searchable,
    count_works,
    get_counts,
    read_cached_counts,
    refresh_stats,
)
from crossref_local._core.store import (
    citations_store,
    corpus_stats_store,
    works_store,
)

#: Shape of the seeded corpus: 5 works, of which 3 carry searchable text.
WORKS_ROWS = 5
SEARCHABLE_ROWS = 3
CITATION_ROWS = 7

#: Distinct stamps planted on the three cache rows, oldest first.
_STAMPS = (
    "2020-01-01T00:00:00+00:00",
    "2021-01-01T00:00:00+00:00",
    "2022-01-01T00:00:00+00:00",
)


@pytest.fixture
def seeded(store_env):
    """Seed the throwaway store with a countable corpus."""
    from scitex_dev.store import NEW_RECORD

    works = works_store()
    for index in range(SEARCHABLE_ROWS):
        works.put(
            {"doi": f"10.1234/work{index}", "title": f"Title {index}"},
            expected_revision=NEW_RECORD,
        )
    for index in range(SEARCHABLE_ROWS, WORKS_ROWS):
        works.put({"doi": f"10.1234/work{index}"}, expected_revision=NEW_RECORD)

    citations = citations_store()
    for index in range(CITATION_ROWS):
        citations.put(
            {"citing_doi": f"10.1234/work{index}", "cited_doi": "10.1234/work0"},
            expected_revision=NEW_RECORD,
        )
    return store_env


# ---------- the counters ----------


def test_count_works_returns_the_exact_number_of_records(seeded):
    # Arrange
    # Act
    total = count_works()
    # Assert
    assert total == WORKS_ROWS


def test_count_searchable_excludes_works_with_no_text(seeded):
    # Arrange — a work with neither title, abstract nor authors cannot be
    # returned by any query, so counting it would overstate reach.
    # Act
    total = count_searchable()
    # Assert
    assert total == SEARCHABLE_ROWS


def test_count_citations_returns_the_exact_number_of_edges(seeded):
    # Arrange
    # Act
    total = count_citations()
    # Assert
    assert total == CITATION_ROWS


# ---------- read path: no cache ----------


def test_read_cached_counts_returns_none_without_a_cache(seeded):
    # Arrange
    # Act
    cached = read_cached_counts()
    # Assert
    assert cached is None


@pytest.fixture
def partial_cache(seeded):
    """Write a cache entry for ONE of the three tracked collections."""
    from scitex_dev.store import NEW_RECORD

    corpus_stats_store().put(
        {"collection": "works", "row_count": WORKS_ROWS, "computed_at": _STAMPS[0]},
        expected_revision=NEW_RECORD,
    )
    return seeded


def test_read_cached_counts_returns_none_on_a_partial_cache(partial_cache):
    # Arrange — partial coverage is not a usable answer; reporting the one
    # collection it has and zero for the rest would be a fabricated number.
    # Act
    cached = read_cached_counts()
    # Assert
    assert cached is None


def test_get_counts_labels_the_source_unavailable_without_a_cache(seeded):
    # Arrange
    # Act
    counts = get_counts()
    # Assert
    assert counts["counts_source"] == "unavailable"


def test_get_counts_reports_no_timestamp_without_a_cache(seeded):
    # Arrange
    # Act
    counts = get_counts()
    # Assert
    assert counts["counts_computed_at"] is None


def test_get_counts_explains_how_to_populate_the_cache(seeded):
    # Arrange
    # Act
    counts = get_counts()
    # Assert
    assert "sync-stats" in counts["note"]


@pytest.fixture
def cache_rows_after_get_counts(seeded):
    """Call the read path, then hand back the cache collection's records."""
    get_counts()
    return corpus_stats_store().rows()


def test_get_counts_never_writes_to_the_cache_collection(cache_rows_after_get_counts):
    # Arrange — the read path must not write: it runs on read-only replicas
    # and on every ``info()`` / ``/health`` call.
    # Act
    written = cache_rows_after_get_counts
    # Assert
    assert written == []


# ---------- write path: refresh_stats() ----------


@pytest.fixture
def refreshed(seeded):
    """Run the write path once and return what it reported."""
    return refresh_stats()


def test_refresh_stats_reports_the_exact_works_count(refreshed):
    # Arrange
    # Act
    # Assert
    assert refreshed["works"] == WORKS_ROWS


def test_refresh_stats_reports_the_exact_searchable_count(refreshed):
    # Arrange
    # Act
    # Assert
    assert refreshed["fts_indexed"] == SEARCHABLE_ROWS


def test_refresh_stats_reports_the_exact_citation_count(refreshed):
    # Arrange
    # Act
    # Assert
    assert refreshed["citations"] == CITATION_ROWS


def test_refresh_stats_labels_the_source_exact(refreshed):
    # Arrange
    # Act
    # Assert
    assert refreshed["counts_source"] == "exact"


def test_refresh_stats_records_a_computed_at_timestamp(refreshed):
    # Arrange
    # Act
    # Assert
    assert refreshed["counts_computed_at"] is not None


def test_refresh_stats_writes_one_cache_row_per_tracked_collection(refreshed):
    # Arrange
    # Act
    rows = corpus_stats_store().rows()
    # Assert
    assert len(rows) == len(STATS_COLLECTIONS)


def test_refresh_stats_reports_zero_for_an_empty_collection(store_env):
    # Arrange — nothing seeded: an empty collection counts as zero, which is
    # the convention info() has always used for an absent table.
    # Act
    counts = refresh_stats()
    # Assert
    assert counts["works"] == 0


def test_refresh_stats_reflects_a_later_write_exactly(refreshed):
    # Arrange
    from scitex_dev.store import NEW_RECORD

    works_store().put({"doi": "10.1234/extra"}, expected_revision=NEW_RECORD)
    # Act
    counts = refresh_stats()
    # Assert
    assert counts["works"] == WORKS_ROWS + 1


# ---------- read path: with a cache ----------


def test_get_counts_labels_the_source_exact_with_a_cache(refreshed):
    # Arrange
    # Act
    counts = get_counts()
    # Assert
    assert counts["counts_source"] == "exact"


def test_get_counts_reports_the_cached_works_count(refreshed):
    # Arrange
    # Act
    counts = get_counts()
    # Assert
    assert counts["works"] == WORKS_ROWS


@pytest.fixture
def sentinel_cache(refreshed):
    """Overwrite the cached works count with a value nothing could compute."""
    from scitex_dev.store import ANY_REVISION

    corpus_stats_store().put(
        {"collection": "works", "row_count": 424242, "computed_at": _STAMPS[1]},
        expected_revision=ANY_REVISION,
    )
    return refreshed


def test_get_counts_returns_the_cached_value_rather_than_recomputing(sentinel_cache):
    # Arrange — 424242 is not the corpus size, so a number that came back
    # unchanged proves the cache was READ, not re-derived.
    # Act
    counts = get_counts()
    # Assert
    assert counts["works"] == 424242


@pytest.fixture
def staggered_cache(seeded):
    """Plant the three cache rows with deliberately different stamps."""
    from scitex_dev.store import NEW_RECORD

    cache = corpus_stats_store()
    for (key, _public), stamp in zip(STATS_COLLECTIONS, _STAMPS):
        cache.put(
            {"collection": key, "row_count": 1, "computed_at": stamp},
            expected_revision=NEW_RECORD,
        )
    return seeded


def test_counts_computed_at_reports_the_oldest_stamp(staggered_cache):
    # Arrange — the honest age of the cache is that of its least-fresh entry.
    # Act
    counts = get_counts()
    # Assert
    assert counts["counts_computed_at"] == _STAMPS[0]


# ---------- info() end to end ----------


@pytest.fixture
def db_mode_info(seeded):
    """``info()`` in db mode against the throwaway store."""
    Config.reset()
    Config.set_mode("db")
    try:
        yield crossref_local.info
    finally:
        Config.reset()


def test_info_reports_the_store_it_would_read(db_mode_info):
    # Arrange
    # Act
    result = db_mode_info()
    # Assert
    assert "store" in result


def test_info_keeps_the_collection_count_keys(db_mode_info):
    # Arrange
    expected = {"works", "fts_indexed", "citations", "mode", "status"}
    # Act
    result = db_mode_info()
    # Assert
    assert expected <= set(result)


def test_info_labels_counts_unavailable_without_a_cache(db_mode_info):
    # Arrange
    # Act
    result = db_mode_info()
    # Assert
    assert result["counts_source"] == "unavailable"


@pytest.fixture
def db_mode_info_with_cache(db_mode_info):
    """``info()`` after the exact-count cache has been written."""
    refresh_stats()
    return db_mode_info


def test_info_labels_counts_exact_once_the_cache_exists(db_mode_info_with_cache):
    # Arrange
    # Act
    result = db_mode_info_with_cache()
    # Assert
    assert result["counts_source"] == "exact"


def test_info_reports_the_exact_citation_count_from_the_cache(db_mode_info_with_cache):
    # Arrange
    # Act
    result = db_mode_info_with_cache()
    # Assert
    assert result["citations"] == CITATION_ROWS

# EOF
