"""Tests for crossref_local._core.store (schemas + openers).

Successor to ``test_db.py``, which tested a connection layer that no longer
exists: it asserted the cursor was a particular driver type, queried a
system catalog and ran a schema pragma. None of those questions have an
answer now — there is no cursor, no catalog to ask and no pragma. What
replaced them is a declaration module and five openers, so this file tests
those: the openers hand back a real ``Store``, the schemas declare the
identity fields the rest of the package keys on, a round-trip preserves a
JSON ``metadata`` dict, an undeclared field is REFUSED rather than dropped,
and ``close_stores()`` releases without breaking the next call.

Every test runs inside a throwaway schema (the ``store_env`` fixture in
``tests/conftest.py``), so nothing here can reach the production store.
"""

import pytest

from crossref_local._core.store import (
    CITATIONS,
    CORPUS_STATS,
    JOURNALS,
    SYNC_STATE,
    WORKS,
    citations_store,
    close_stores,
    corpus_stats_store,
    journals_store,
    node_id,
    sync_state_store,
    works_store,
)


# ---------- openers return a real Store ----------


@pytest.mark.parametrize(
    "opener",
    [
        works_store,
        citations_store,
        journals_store,
        corpus_stats_store,
        sync_state_store,
    ],
)
def test_every_opener_returns_a_store_instance(store_env, opener):
    # Arrange
    from scitex_dev.store import Store

    # Act
    store = opener()
    # Assert
    assert isinstance(store, Store)


def test_repeat_opener_call_reuses_the_same_store_on_one_thread(store_env):
    # Arrange
    first = works_store()
    # Act
    second = works_store()
    # Assert
    assert first is second


def test_node_id_is_a_non_empty_string():
    # Arrange
    # Act
    node = node_id()
    # Assert
    assert isinstance(node, str) and node


# ---------- schemas declare the identity the package keys on ----------


def test_works_schema_is_keyed_by_doi_alone():
    # Arrange
    schema = WORKS
    # Act
    identity = schema.identity_fields
    # Assert
    assert identity == ("doi",)


def test_citations_schema_is_keyed_by_the_citing_cited_pair():
    # Arrange
    schema = CITATIONS
    # Act
    identity = schema.identity_fields
    # Assert
    assert identity == ("citing_doi", "cited_doi")


def test_journals_schema_is_keyed_by_issn_l():
    # Arrange
    schema = JOURNALS
    # Act
    identity = schema.identity_fields
    # Assert
    assert identity == ("issn_l",)


def test_corpus_stats_schema_is_keyed_by_collection():
    # Arrange
    schema = CORPUS_STATS
    # Act
    identity = schema.identity_fields
    # Assert
    assert identity == ("collection",)


def test_sync_state_schema_is_keyed_by_key():
    # Arrange
    schema = SYNC_STATE
    # Act
    identity = schema.identity_fields
    # Assert
    assert identity == ("key",)


def test_works_schema_declares_the_denormalised_search_fields():
    # Arrange — search reads these directly; they replaced the old
    # separate full-text table.
    expected = {"title", "abstract", "authors", "container_title"}
    # Act
    declared = set(WORKS.fields)
    # Assert
    assert expected <= declared


# ---------- round-trip ----------


@pytest.fixture
def seeded_work(store_env):
    """Write one work and return (store, doi, metadata)."""
    from scitex_dev.store import NEW_RECORD

    metadata = {
        "DOI": "10.1000/store.roundtrip",
        "title": ["A Round Trip"],
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "nested": {"list": [1, 2, 3], "flag": True},
    }
    store = works_store()
    store.put(
        {
            "doi": "10.1000/store.roundtrip",
            "metadata": metadata,
            "title": "A Round Trip",
            "year": 2026,
        },
        expected_revision=NEW_RECORD,
    )
    return store, "10.1000/store.roundtrip", metadata


def test_put_then_get_returns_the_written_row(seeded_work):
    # Arrange
    store, doi, _metadata = seeded_work
    # Act
    row = store.get({"doi": doi})
    # Assert
    assert row is not None


def test_get_returns_the_identity_field_verbatim(seeded_work):
    # Arrange
    store, doi, _metadata = seeded_work
    # Act
    row = store.get({"doi": doi})
    # Assert
    assert row.values["doi"] == doi


def test_json_metadata_comes_back_as_a_dict_not_a_string(seeded_work):
    # Arrange
    store, doi, _metadata = seeded_work
    # Act
    row = store.get({"doi": doi})
    # Assert
    assert isinstance(row.values["metadata"], dict)


def test_json_metadata_round_trips_nested_structure_unchanged(seeded_work):
    # Arrange
    store, doi, metadata = seeded_work
    # Act
    row = store.get({"doi": doi})
    # Assert
    assert row.values["metadata"] == metadata


def test_integer_field_round_trips_as_an_integer(seeded_work):
    # Arrange
    store, doi, _metadata = seeded_work
    # Act
    row = store.get({"doi": doi})
    # Assert
    assert row.values["year"] == 2026


def test_get_returns_none_for_a_key_never_written(store_env):
    # Arrange
    store = works_store()
    # Act
    row = store.get({"doi": "10.9999/never.written"})
    # Assert
    assert row is None


def test_rows_returns_every_written_record(seeded_work):
    # Arrange
    store, _doi, _metadata = seeded_work
    # Act
    rows = store.rows()
    # Assert
    assert len(rows) == 1


# ---------- an undeclared field is refused, never dropped ----------


def test_put_raises_on_a_field_the_schema_does_not_declare(store_env):
    # Arrange
    from scitex_dev.store import NEW_RECORD

    store = works_store()
    values = {"doi": "10.1000/store.undeclared", "impact_factor": 42.0}
    # Act
    ctx = pytest.raises(Exception)
    # Assert
    with ctx:
        store.put(values, expected_revision=NEW_RECORD)


@pytest.fixture
def store_after_refused_put(store_env):
    """A store on which a put carrying an undeclared field was refused."""
    import contextlib

    from scitex_dev.store import NEW_RECORD

    store = works_store()
    with contextlib.suppress(Exception):
        store.put(
            {"doi": "10.1000/store.undeclared", "impact_factor": 42.0},
            expected_revision=NEW_RECORD,
        )
    return store


def test_refused_put_writes_no_record_at_all(store_after_refused_put):
    # Arrange
    doi = "10.1000/store.undeclared"
    # Act
    row = store_after_refused_put.get({"doi": doi})
    # Assert
    assert row is None


# ---------- composite identity ----------


@pytest.fixture
def seeded_edge(store_env):
    """Write one citation edge under its composite key."""
    from scitex_dev.store import NEW_RECORD

    store = citations_store()
    store.put(
        {
            "citing_doi": "10.1000/store.citing",
            "cited_doi": "10.1000/store.cited",
            "citing_year": 2024,
        },
        expected_revision=NEW_RECORD,
    )
    return store


def test_composite_key_get_returns_the_edge(seeded_edge):
    # Arrange
    key = {"citing_doi": "10.1000/store.citing", "cited_doi": "10.1000/store.cited"}
    # Act
    row = seeded_edge.get(key)
    # Assert
    assert row is not None


def test_composite_key_get_preserves_the_edge_payload(seeded_edge):
    # Arrange
    key = {"citing_doi": "10.1000/store.citing", "cited_doi": "10.1000/store.cited"}
    # Act
    row = seeded_edge.get(key)
    # Assert
    assert row.values["citing_year"] == 2024


def test_composite_key_get_misses_when_only_one_half_matches(seeded_edge):
    # Arrange — the PAIR is the identity, so half of it is a different key.
    key = {"citing_doi": "10.1000/store.citing", "cited_doi": "10.1000/store.other"}
    # Act
    row = seeded_edge.get(key)
    # Assert
    assert row is None


def test_rewriting_the_same_edge_is_idempotent(seeded_edge):
    # Arrange
    from scitex_dev.store import ANY_REVISION

    # Act
    seeded_edge.put(
        {
            "citing_doi": "10.1000/store.citing",
            "cited_doi": "10.1000/store.cited",
            "citing_year": 2025,
        },
        expected_revision=ANY_REVISION,
    )
    # Assert
    assert len(seeded_edge.rows()) == 1


# ---------- close_stores() ----------


def test_close_stores_hands_back_a_fresh_store_on_the_next_call(store_env):
    # Arrange
    first = works_store()
    # Act
    close_stores()
    second = works_store()
    # Assert
    assert second is not first


def test_close_stores_does_not_lose_written_records(seeded_work):
    # Arrange
    _store, doi, _metadata = seeded_work
    # Act
    close_stores()
    row = works_store().get({"doi": doi})
    # Assert
    assert row is not None


def test_close_stores_is_safe_to_call_twice(store_env):
    # Arrange
    works_store()
    # Act
    close_stores()
    close_stores()
    # Assert
    assert works_store() is not None

# EOF
