"""Tests for crossref_local.server module (FastAPI HTTP server)."""

import pytest

# PA-303: fastapi is in [api]/[dev] extras, not [project] dependencies
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from crossref_local.server import app


@pytest.fixture
def client():
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def real_doi_from_search(client):
    """Resolve a real DOI by hitting /works; skip if none found."""
    response = client.get("/works?q=test&limit=1")
    if response.status_code != 200:
        pytest.skip("could not resolve a sample DOI via /works")
    results = response.json().get("results", [])
    if not results:
        pytest.skip("no /works results to derive a DOI from")
    return results[0]["doi"]


@pytest.fixture
def batch_dois(client):
    """Resolve several DOIs for batch tests; skip if too few."""
    response = client.get("/works?q=science&limit=3")
    if response.status_code != 200:
        pytest.skip("could not collect a batch of DOIs from /works")
    results = response.json().get("results", [])
    if not results:
        pytest.skip("no /works results to derive batch DOIs from")
    return [w["doi"] for w in results]


# ---------- / ----------


def test_root_endpoint_returns_200_status(client):
    # Arrange
    # Act
    response = client.get("/")
    # Assert
    assert response.status_code == 200


def test_root_endpoint_response_contains_name_field(client):
    # Arrange
    # Act
    data = client.get("/").json()
    # Assert
    assert "name" in data


def test_root_endpoint_response_contains_version_field(client):
    # Arrange
    # Act
    data = client.get("/").json()
    # Assert
    assert "version" in data


def test_root_endpoint_response_contains_endpoints_field(client):
    # Arrange
    # Act
    data = client.get("/").json()
    # Assert
    assert "endpoints" in data


def test_root_endpoint_endpoints_dict_lists_health(client):
    # Arrange
    # Act
    endpoints = client.get("/").json()["endpoints"]
    # Assert
    assert "health" in endpoints


def test_root_endpoint_endpoints_dict_lists_info(client):
    # Arrange
    # Act
    endpoints = client.get("/").json()["endpoints"]
    # Assert
    assert "info" in endpoints


# ---------- /health ----------


def test_health_endpoint_returns_200_status(client):
    # Arrange
    # Act
    response = client.get("/health")
    # Assert
    assert response.status_code == 200


def test_health_endpoint_reports_status_healthy(client):
    # Arrange
    # Act
    data = client.get("/health").json()
    # Assert
    assert data["status"] == "healthy"


def test_health_endpoint_includes_store_field(client):
    # Arrange — `database_connected` became `store`: the probe resolves a
    # target rather than opening a connection, so what it can honestly
    # report is WHICH store, not whether a socket is up.
    # Act
    data = client.get("/health").json()
    # Assert
    assert "store" in data


# ---------- /info ----------


def test_info_endpoint_returns_200_status(client):
    # Arrange
    # Act
    response = client.get("/info")
    # Assert
    assert response.status_code == 200


def test_info_endpoint_includes_total_papers_field(client):
    # Arrange
    # Act
    data = client.get("/info").json()
    # Assert
    assert "total_papers" in data


def test_info_endpoint_includes_fts_indexed_field(client):
    # Arrange
    # Act
    data = client.get("/info").json()
    # Assert
    assert "fts_indexed" in data


def test_info_endpoint_total_papers_field_is_integer(client):
    # Arrange
    # Act
    data = client.get("/info").json()
    # Assert
    assert isinstance(data["total_papers"], int)


def test_info_endpoint_includes_counts_source_field(client):
    # Arrange
    # Act
    data = client.get("/info").json()
    # Assert
    assert "counts_source" in data


def test_info_endpoint_counts_source_is_honest_label(client):
    # Arrange
    # Act
    data = client.get("/info").json()
    # Assert — cache-backed "exact", or "unavailable" when no cache has
    # been written; never a silent full-collection scan on the read path.
    assert data["counts_source"] in {"exact", "unavailable"}


# ---------- /works search ----------


def test_works_search_requires_q_parameter_returns_422(client):
    # Arrange
    # Act
    response = client.get("/works")
    # Assert
    assert response.status_code == 422


def test_works_search_with_query_returns_200(client):
    # Arrange
    # Act
    response = client.get("/works?q=cancer&limit=3")
    # Assert
    assert response.status_code == 200


def test_works_search_response_contains_query_field(client):
    # Arrange
    # Act
    data = client.get("/works?q=cancer&limit=3").json()
    # Assert
    assert "query" in data


def test_works_search_response_contains_total_field(client):
    # Arrange
    # Act
    data = client.get("/works?q=cancer&limit=3").json()
    # Assert
    assert "total" in data


def test_works_search_response_contains_results_field(client):
    # Arrange
    # Act
    data = client.get("/works?q=cancer&limit=3").json()
    # Assert
    assert "results" in data


def test_works_search_query_field_echoes_supplied_q_parameter(client):
    # Arrange
    # Act
    data = client.get("/works?q=cancer&limit=3").json()
    # Assert
    assert data["query"] == "cancer"


def test_works_search_results_length_respects_limit_parameter(client):
    # Arrange
    # Act
    data = client.get("/works?q=biology&limit=5").json()
    # Assert
    assert len(data["results"]) <= 5


def test_works_search_response_includes_elapsed_ms_field(client):
    # Arrange
    # Act
    data = client.get("/works?q=physics&limit=1").json()
    # Assert
    assert "elapsed_ms" in data


def test_works_search_elapsed_ms_field_is_number_type(client):
    # Arrange
    # Act
    data = client.get("/works?q=physics&limit=1").json()
    # Assert
    assert isinstance(data["elapsed_ms"], (int, float))


def test_works_search_every_result_has_doi_field(client):
    # Arrange
    # Act
    data = client.get("/works?q=medicine&limit=3").json()
    # Assert
    assert all("doi" in w for w in data["results"])


def test_works_search_every_result_doi_starts_with_10(client):
    # Arrange
    # Act
    data = client.get("/works?q=medicine&limit=3").json()
    # Assert
    assert all(w["doi"].startswith("10.") for w in data["results"])


# ---------- /works/{doi} ----------


def test_works_get_endpoint_returns_404_for_unknown_doi(client):
    # Arrange
    # Act
    response = client.get("/works/10.9999/nonexistent")
    # Assert
    assert response.status_code == 404


def test_works_get_endpoint_returns_200_for_known_doi(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    response = client.get(f"/works/{doi}")
    # Assert
    assert response.status_code == 200


def test_works_get_endpoint_returns_matching_doi_field(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/works/{doi}").json()
    # Assert
    assert data["doi"] == doi


# ---------- /works/batch ----------


def test_works_batch_endpoint_returns_200_for_real_dois(client, batch_dois):
    # Arrange
    # Act
    response = client.post("/works/batch", json={"dois": batch_dois})
    # Assert
    assert response.status_code == 200


def test_works_batch_endpoint_response_contains_requested_field(client, batch_dois):
    # Arrange
    # Act
    data = client.post("/works/batch", json={"dois": batch_dois}).json()
    # Assert
    assert "requested" in data


def test_works_batch_endpoint_response_contains_found_field(client, batch_dois):
    # Arrange
    # Act
    data = client.post("/works/batch", json={"dois": batch_dois}).json()
    # Assert
    assert "found" in data


def test_works_batch_endpoint_response_contains_results_field(client, batch_dois):
    # Arrange
    # Act
    data = client.post("/works/batch", json={"dois": batch_dois}).json()
    # Assert
    assert "results" in data


def test_works_batch_endpoint_empty_list_returns_200_status(client):
    # Arrange
    # Act
    response = client.post("/works/batch", json={"dois": []})
    # Assert
    assert response.status_code == 200


def test_works_batch_endpoint_empty_list_reports_requested_zero(client):
    # Arrange
    # Act
    data = client.post("/works/batch", json={"dois": []}).json()
    # Assert
    assert data["requested"] == 0


def test_works_batch_endpoint_empty_list_reports_found_zero(client):
    # Arrange
    # Act
    data = client.post("/works/batch", json={"dois": []}).json()
    # Assert
    assert data["found"] == 0


# ---------- /citations/{doi}/citing ----------


def test_citations_citing_endpoint_returns_200_status(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    response = client.get(f"/citations/{doi}/citing?limit=10")
    # Assert
    assert response.status_code == 200


def test_citations_citing_response_contains_papers_list(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/citing?limit=10").json()
    # Assert
    assert isinstance(data["papers"], list)


def test_citations_citing_response_contains_citing_count_field(
    client, real_doi_from_search
):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/citing?limit=10").json()
    # Assert
    assert "citing_count" in data


# ---------- /citations/{doi}/cited ----------


def test_citations_cited_endpoint_returns_200_status(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    response = client.get(f"/citations/{doi}/cited?limit=10")
    # Assert
    assert response.status_code == 200


def test_citations_cited_response_contains_papers_list(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/cited?limit=10").json()
    # Assert
    assert isinstance(data["papers"], list)


def test_citations_cited_response_contains_cited_count_field(
    client, real_doi_from_search
):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/cited?limit=10").json()
    # Assert
    assert "cited_count" in data


# ---------- /citations/{doi}/count ----------


def test_citations_count_endpoint_returns_200_status(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    response = client.get(f"/citations/{doi}/count")
    # Assert
    assert response.status_code == 200


def test_citations_count_response_includes_doi_field(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/count").json()
    # Assert
    assert "doi" in data


def test_citations_count_citation_count_field_is_integer_type(
    client, real_doi_from_search
):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/count").json()
    # Assert
    assert isinstance(data["citation_count"], int)


# ---------- /citations/{doi}/network ----------


def test_citations_network_endpoint_returns_200_status(client, real_doi_from_search):
    # Arrange
    doi = real_doi_from_search
    # Act
    response = client.get(f"/citations/{doi}/network?depth=1")
    # Assert
    assert response.status_code == 200


def test_citations_network_response_contains_center_doi(
    client, real_doi_from_search
):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/network?depth=1").json()
    # Assert
    assert "center_doi" in data


def test_citations_network_response_nodes_field_is_list(
    client, real_doi_from_search
):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/network?depth=1").json()
    # Assert
    assert isinstance(data["nodes"], list)


def test_citations_network_response_edges_field_is_list(
    client, real_doi_from_search
):
    # Arrange
    doi = real_doi_from_search
    # Act
    data = client.get(f"/citations/{doi}/network?depth=1").json()
    # Assert
    assert isinstance(data["edges"], list)


# ---------- backwards-compatible /api/* endpoints ----------


def test_api_search_legacy_endpoint_returns_200_status(client):
    # Arrange
    # Act
    response = client.get("/api/search/?q=cancer&limit=3")
    # Assert
    assert response.status_code == 200


def test_api_search_legacy_response_contains_results_field(client):
    # Arrange
    # Act
    data = client.get("/api/search/?q=cancer&limit=3").json()
    # Assert
    assert "results" in data


def test_api_search_legacy_response_contains_total_field(client):
    # Arrange
    # Act
    data = client.get("/api/search/?q=cancer&limit=3").json()
    # Assert
    assert "total" in data


def test_api_stats_legacy_endpoint_returns_200_status(client):
    # Arrange
    # Act
    response = client.get("/api/stats/")
    # Assert
    assert response.status_code == 200


def test_api_stats_legacy_response_contains_total_papers_field(client):
    # Arrange
    # Act
    data = client.get("/api/stats/").json()
    # Assert
    assert "total_papers" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
