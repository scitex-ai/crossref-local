"""Tests for crossref_local.api module."""

import pytest

from crossref_local import count, enrich, enrich_dois, exists, get, info, search
from crossref_local._core.models import SearchResult, Work


# ---------- search() ----------


def test_search_returns_search_result_instance():
    # Arrange
    # Act
    results = search("neuroscience", limit=1)
    # Assert
    assert isinstance(results, SearchResult)


def test_search_result_exposes_query_attribute():
    # Arrange
    # Act
    results = search("neuroscience", limit=1)
    # Assert
    assert hasattr(results, "query")


def test_search_result_exposes_total_attribute():
    # Arrange
    # Act
    results = search("neuroscience", limit=1)
    # Assert
    assert hasattr(results, "total")


def test_search_result_exposes_elapsed_ms_attribute():
    # Arrange
    # Act
    results = search("neuroscience", limit=1)
    # Assert
    assert hasattr(results, "elapsed_ms")


def test_search_result_exposes_works_attribute():
    # Arrange
    # Act
    results = search("neuroscience", limit=1)
    # Assert
    assert hasattr(results, "works")


def test_search_returns_only_work_instances_in_works_collection():
    # Arrange
    # Act
    results = search("cancer", limit=3)
    # Assert
    assert all(isinstance(w, Work) for w in results.works)


def test_search_results_works_length_respects_limit_argument():
    # Arrange
    limit = 5
    # Act
    results = search("neuroscience", limit=limit)
    # Assert
    assert len(results.works) <= limit


@pytest.fixture
def _neuroscience_paging():
    """Two pages of neuroscience hits, or skip if the fixture is too small."""
    first = search("neuroscience", limit=5, offset=0)
    if len(first.works) < 5:
        pytest.skip("not enough hits to validate offset semantics")
    second = search("neuroscience", limit=5, offset=5)
    if not second.works:
        pytest.skip("offset page is empty in this fixture")
    return first, second


def test_search_with_offset_returns_distinct_first_doi_from_first_page(
    _neuroscience_paging,
):
    # Arrange
    first, second = _neuroscience_paging
    # Act
    same = first.works[0].doi == second.works[0].doi
    # Assert
    assert not same


# ---------- get() ----------


@pytest.fixture
def _known_doi_from_search():
    results = search("neuroscience", limit=1)
    if not results.works:
        pytest.skip("no hits available to derive a DOI")
    return results.works[0].doi


def test_get_returns_non_none_for_known_doi(_known_doi_from_search):
    # Arrange
    # Act
    work = get(_known_doi_from_search)
    # Assert
    assert work is not None


def test_get_returns_work_instance_for_known_doi(_known_doi_from_search):
    # Arrange
    # Act
    work = get(_known_doi_from_search)
    # Assert
    assert isinstance(work, Work)


def test_get_returned_work_doi_matches_input(_known_doi_from_search):
    # Arrange
    doi = _known_doi_from_search
    # Act
    work = get(doi)
    # Assert
    assert work.doi == doi


def test_get_returns_none_for_doi_absent_from_database():
    # Arrange
    # Act
    work = get("10.9999/nonexistent.doi.12345")
    # Assert
    assert work is None


# ---------- count() ----------


def test_count_returns_integer_type_for_known_term():
    # Arrange
    # Act
    n = count("neuroscience")
    # Assert
    assert isinstance(n, int)


def test_count_returns_positive_value_for_known_term():
    # Arrange
    # Act
    n = count("neuroscience")
    # Assert
    assert n > 0


def test_count_returns_positive_value_for_cancer_query():
    # Arrange
    # Act
    n = count("cancer")
    # Assert
    assert n > 0


# ---------- exists() ----------


@pytest.fixture
def _quantum_doi():
    results = search("quantum", limit=1)
    if not results.works:
        pytest.skip("no quantum hits in fixture DB")
    return results.works[0].doi


def test_exists_returns_true_for_known_doi(_quantum_doi):
    # Arrange
    doi = _quantum_doi
    # Act
    present = exists(doi)
    # Assert
    assert present is True


def test_exists_returns_false_for_doi_absent_from_database():
    # Arrange
    # Act
    present = exists("10.9999/nonexistent")
    # Assert
    assert present is False


# ---------- info() ----------


@pytest.fixture
def _db_info():
    return info()


def test_info_returns_dict_instance(_db_info):
    # Arrange
    # Act
    # Assert
    assert isinstance(_db_info, dict)


def test_info_dict_contains_db_path_key(_db_info):
    # Arrange
    # Act
    # Assert
    assert "db_path" in _db_info


def test_info_dict_contains_works_key(_db_info):
    # Arrange
    # Act
    # Assert
    assert "works" in _db_info


def test_info_dict_contains_fts_indexed_key(_db_info):
    # Arrange
    # Act
    # Assert
    assert "fts_indexed" in _db_info


def test_info_dict_contains_citations_key(_db_info):
    # Arrange
    # Act
    # Assert
    assert "citations" in _db_info


def test_info_dict_reports_positive_works_count(_db_info):
    # Arrange
    # Act
    # Assert
    assert _db_info["works"] > 0


def test_info_dict_contains_counts_source_key(_db_info):
    # Arrange
    # Act
    # Assert
    assert "counts_source" in _db_info


def test_info_counts_source_is_honest_label(_db_info):
    # Arrange
    # Act
    # Assert
    assert _db_info["counts_source"] in {"exact", "estimated", "unavailable"}


# ---------- enrich() ----------


def test_enrich_returns_search_result_instance():
    # Arrange
    results = search("neuroscience", limit=2)
    # Act
    enriched = enrich(results)
    # Assert
    assert isinstance(enriched, SearchResult)


def test_enrich_preserves_total_from_input_search_result():
    # Arrange
    results = search("cancer", limit=3)
    # Act
    enriched = enrich(results)
    # Assert
    assert enriched.total == results.total


@pytest.fixture
def _quantum_search_result():
    results = search("quantum", limit=1)
    if not results.works:
        pytest.skip("no quantum hits in fixture DB")
    return results


def test_enrich_preserves_works_count_from_input_search_result(_quantum_search_result):
    # Arrange
    results = _quantum_search_result
    # Act
    enriched = enrich(results)
    # Assert
    assert len(enriched.works) == len(results.works)


# ---------- enrich_dois() ----------


@pytest.fixture
def _ml_dois():
    results = search("machine learning", limit=2)
    if not results.works:
        pytest.skip("no machine-learning hits in fixture DB")
    return [w.doi for w in results.works]


def test_enrich_dois_returns_list_instance(_ml_dois):
    # Arrange
    # Act
    works = enrich_dois(_ml_dois)
    # Assert
    assert isinstance(works, list)


def test_enrich_dois_returns_only_work_instances(_ml_dois):
    # Arrange
    # Act
    works = enrich_dois(_ml_dois)
    # Assert
    assert all(isinstance(w, Work) for w in works)


@pytest.fixture
def _neuroscience_dois():
    results = search("neuroscience", limit=3)
    if not results.works:
        pytest.skip("no neuroscience hits in fixture DB")
    return [w.doi for w in results.works]


def test_enrich_dois_returns_no_more_works_than_dois_supplied(_neuroscience_dois):
    # Arrange
    dois = _neuroscience_dois
    # Act
    works = enrich_dois(dois)
    # Assert
    assert len(works) <= len(dois)


def test_enrich_dois_with_empty_list_returns_empty_list():
    # Arrange
    # Act
    works = enrich_dois([])
    # Assert
    assert works == []


if __name__ == "__main__":
    import os

    pytest.main([os.path.abspath(__file__)])
