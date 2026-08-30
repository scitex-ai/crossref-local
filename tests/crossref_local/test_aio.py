"""Tests for crossref_local.aio module (async API)."""

import asyncio

import pytest

from crossref_local import aio
from crossref_local._core.models import SearchResult, Work


# ---------- aio.search ----------


@pytest.mark.asyncio
async def test_aio_search_returns_search_result_instance():
    # Arrange
    # Act
    results = await aio.search("science", limit=1)
    # Assert
    assert isinstance(results, SearchResult)


@pytest.mark.asyncio
async def test_aio_search_result_query_matches_supplied_string():
    # Arrange
    query = "biology"
    # Act
    results = await aio.search(query, limit=1)
    # Assert
    assert results.query == query


@pytest.mark.asyncio
async def test_aio_search_result_total_is_integer_type():
    # Arrange
    # Act
    results = await aio.search("medicine", limit=1)
    # Assert
    assert isinstance(results.total, int)


@pytest.mark.asyncio
async def test_aio_search_result_total_is_nonnegative():
    # Arrange
    # Act
    results = await aio.search("medicine", limit=1)
    # Assert
    assert results.total >= 0


@pytest.mark.asyncio
async def test_aio_search_yields_work_objects_for_every_hit():
    # Arrange
    # Act
    results = await aio.search("chemistry", limit=3)
    # Assert
    assert all(isinstance(w, Work) for w in results.works)


@pytest.mark.asyncio
async def test_aio_search_respects_limit_argument_on_returned_works():
    # Arrange
    limit = 5
    # Act
    results = await aio.search("cancer", limit=limit)
    # Assert
    assert len(results.works) <= limit


@pytest.fixture
async def _aio_neuroscience_paging():
    """Return (page1, page2) for offset paging, or skip if too few hits."""
    page1 = await aio.search("neuroscience", limit=5, offset=0)
    if len(page1.works) < 5:
        pytest.skip("not enough hits for paging assertion")
    page2 = await aio.search("neuroscience", limit=5, offset=5)
    if not page2.works:
        pytest.skip("offset page empty in this fixture")
    return page1, page2


@pytest.mark.asyncio
async def test_aio_search_with_offset_yields_distinct_first_doi_from_page_zero(
    _aio_neuroscience_paging,
):
    # Arrange
    page1, page2 = _aio_neuroscience_paging
    # Act
    same = page1.works[0].doi == page2.works[0].doi
    # Assert
    assert not same


# ---------- aio.count ----------


@pytest.mark.asyncio
async def test_aio_count_returns_integer_type():
    # Arrange
    # Act
    n = await aio.count("science")
    # Assert
    assert isinstance(n, int)


@pytest.mark.asyncio
async def test_aio_count_returns_nonnegative_value_for_known_term():
    # Arrange
    # Act
    n = await aio.count("biology")
    # Assert
    assert n >= 0


@pytest.mark.asyncio
async def test_aio_count_returns_zero_for_nonsense_term_with_no_hits():
    # Arrange
    # Act
    n = await aio.count("xyznonexistent123")
    # Assert
    assert n == 0


# ---------- aio.get ----------


@pytest.mark.asyncio
async def test_aio_get_returns_work_or_none_for_sample_doi(sample_doi):
    # Arrange
    # Act
    work = await aio.get(sample_doi)
    # Assert
    assert work is None or isinstance(work, Work)


@pytest.mark.asyncio
async def test_aio_get_returns_none_for_doi_absent_from_database():
    # Arrange
    # Act
    work = await aio.get("10.0000/nonexistent")
    # Assert
    assert work is None


@pytest.fixture
async def _existing_work(sample_doi):
    work = await aio.get(sample_doi)
    if work is None:
        pytest.skip("sample DOI not present in fixture DB")
    return work


@pytest.mark.asyncio
async def test_aio_get_returned_work_doi_matches_input(_existing_work, sample_doi):
    # Arrange
    work = _existing_work
    # Act
    doi = work.doi
    # Assert
    assert doi == sample_doi


# ---------- aio.get_many ----------


@pytest.mark.asyncio
async def test_aio_get_many_returns_list_instance(sample_doi):
    # Arrange
    # Act
    works = await aio.get_many([sample_doi])
    # Assert
    assert isinstance(works, list)


@pytest.mark.asyncio
async def test_aio_get_many_returns_empty_list_for_empty_input():
    # Arrange
    # Act
    works = await aio.get_many([])
    # Assert
    assert works == []


@pytest.mark.asyncio
async def test_aio_get_many_returns_empty_list_when_all_dois_are_unknown():
    # Arrange
    dois = ["10.0000/nonexistent1", "10.0000/nonexistent2"]
    # Act
    works = await aio.get_many(dois)
    # Assert
    assert works == []


# ---------- aio.exists ----------


@pytest.mark.asyncio
async def test_aio_exists_returns_boolean_type_for_known_doi(sample_doi):
    # Arrange
    # Act
    result = await aio.exists(sample_doi)
    # Assert
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_aio_exists_returns_false_for_doi_absent_from_database():
    # Arrange
    # Act
    result = await aio.exists("10.0000/nonexistent")
    # Assert
    assert result is False


# ---------- aio.info ----------


@pytest.mark.asyncio
async def test_aio_info_returns_dict_instance():
    # Arrange
    # Act
    info = await aio.info()
    # Assert
    assert isinstance(info, dict)


@pytest.mark.asyncio
async def test_aio_info_dict_contains_store_key():
    # Arrange — `db_path` became `store` when the corpus moved off a file.
    # Act
    info = await aio.info()
    # Assert
    assert "store" in info


@pytest.mark.asyncio
async def test_aio_info_dict_contains_works_key():
    # Arrange
    # Act
    info = await aio.info()
    # Assert
    assert "works" in info


@pytest.mark.asyncio
async def test_aio_info_works_value_is_integer_type():
    # Arrange
    # Act
    info = await aio.info()
    # Assert
    assert isinstance(info["works"], int)


# ---------- aio.search_many ----------


@pytest.mark.asyncio
async def test_aio_search_many_returns_list_instance():
    # Arrange
    # Act
    results = await aio.search_many(["science", "biology"], limit=1)
    # Assert
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_aio_search_many_returns_one_entry_per_input_query():
    # Arrange
    queries = ["science", "biology"]
    # Act
    results = await aio.search_many(queries, limit=1)
    # Assert
    assert len(results) == len(queries)


@pytest.mark.asyncio
async def test_aio_search_many_each_entry_is_search_result():
    # Arrange
    queries = ["science", "biology"]
    # Act
    results = await aio.search_many(queries, limit=1)
    # Assert
    assert all(isinstance(r, SearchResult) for r in results)


@pytest.mark.asyncio
async def test_aio_search_many_handles_three_queries_concurrently():
    # Arrange
    queries = ["physics", "chemistry", "biology"]
    # Act
    results = await aio.search_many(queries, limit=1)
    # Assert
    assert len(results) == 3


# ---------- aio.count_many ----------


@pytest.mark.asyncio
async def test_aio_count_many_returns_dict_instance():
    # Arrange
    # Act
    counts = await aio.count_many(["science", "biology"])
    # Assert
    assert isinstance(counts, dict)


@pytest.mark.asyncio
async def test_aio_count_many_keys_include_every_input_query():
    # Arrange
    queries = ["science", "biology"]
    # Act
    counts = await aio.count_many(queries)
    # Assert
    assert set(queries).issubset(counts.keys())


@pytest.mark.asyncio
async def test_aio_count_many_values_are_all_integers():
    # Arrange
    queries = ["physics", "chemistry"]
    # Act
    counts = await aio.count_many(queries)
    # Assert
    assert all(isinstance(c, int) for c in counts.values())


@pytest.mark.asyncio
async def test_aio_count_many_values_are_all_nonnegative():
    # Arrange
    queries = ["physics", "chemistry"]
    # Act
    counts = await aio.count_many(queries)
    # Assert
    assert all(c >= 0 for c in counts.values())


# ---------- concurrency under asyncio.gather ----------


@pytest.mark.asyncio
async def test_asyncio_gather_runs_three_searches_and_returns_three_results():
    # Arrange
    tasks = [
        aio.search("science", limit=1),
        aio.search("biology", limit=1),
        aio.search("physics", limit=1),
    ]
    # Act
    results = await asyncio.gather(*tasks)
    # Assert
    assert len(results) == 3


@pytest.mark.asyncio
async def test_asyncio_gather_three_searches_returns_only_search_result_objects():
    # Arrange
    tasks = [
        aio.search("science", limit=1),
        aio.search("biology", limit=1),
        aio.search("physics", limit=1),
    ]
    # Act
    results = await asyncio.gather(*tasks)
    # Assert
    assert all(isinstance(r, SearchResult) for r in results)


@pytest.mark.asyncio
async def test_asyncio_gather_runs_mixed_operations_and_returns_four_results(
    sample_doi,
):
    # Arrange
    tasks = [
        aio.search("science", limit=1),
        aio.count("biology"),
        aio.get(sample_doi),
        aio.info(),
    ]
    # Act
    results = await asyncio.gather(*tasks)
    # Assert
    assert len(results) == 4
