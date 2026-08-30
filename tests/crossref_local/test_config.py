"""Tests for crossref_local._core.config.

No mocks: environment variables are managed by yield-based save/restore
fixtures, which is how a caller really selects a mode, and the store is a
throwaway schema opened by the ``store_env`` fixture.

WHAT WAS DROPPED. Every ``get_db_path`` / ``Config.set_db_path`` /
``DEFAULT_DB_PATHS`` test went with the functions themselves: the corpus
lives in the shared store, so there is no path to resolve, no
``CROSSREF_LOCAL_DB`` variable naming one, and no auto-discovery list to
walk. DSN resolution belongs to :func:`scitex_dev.store.host_store`, and
this module deliberately keeps no second copy of that answer. What replaced
them — :func:`store_available` and :meth:`Config.describe_store` — is
tested below, including the property that made ``describe_store`` a
separate method rather than "print the DSN": it must never carry a
credential.
"""

import os

import pytest

from crossref_local._core.config import (
    DEFAULT_API_URL,
    DEFAULT_API_URLS,
    DEFAULT_PORT,
    Config,
    store_available,
)


@pytest.fixture
def mode_env():
    """Yield-based save/restore for the two mode environment variables."""
    keys = ("CROSSREF_LOCAL_MODE", "SCITEX_SCHOLAR_CROSSREF_MODE")
    saved = {key: os.environ.get(key) for key in keys}

    def setter(**values):
        for key, value in values.items():
            os.environ[key] = value
        Config.reset()

    Config.reset()
    try:
        yield setter
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        Config.reset()


@pytest.fixture
def clean_config():
    """A Config with no leaked class-level state, restored afterwards."""
    Config.reset()
    try:
        yield Config
    finally:
        Config.reset()


# ---------- store_available() ----------


def test_store_available_returns_a_boolean(clean_config):
    # Arrange
    # Act
    available = store_available()
    # Assert
    assert isinstance(available, bool)


def test_store_available_is_true_when_a_target_resolves(store_env, clean_config):
    # Arrange — resolution only; this must not open a connection.
    # Act
    available = store_available()
    # Assert
    assert available is True


# ---------- Config.describe_store() ----------


def test_describe_store_returns_a_string(store_env, clean_config):
    # Arrange
    # Act
    described = Config.describe_store()
    # Assert
    assert isinstance(described, str)


def test_describe_store_names_the_package_slot(store_env, clean_config):
    # Arrange
    # Act
    described = Config.describe_store()
    # Assert
    assert "crossref_local" in described


def test_describe_store_names_the_works_collection(store_env, clean_config):
    # Arrange
    # Act
    described = Config.describe_store()
    # Assert
    assert "works" in described


def test_describe_store_never_leaks_a_password(store_env, clean_config):
    # Arrange — this value is printed to terminals and returned over HTTP,
    # which is exactly why it is not the DSN.
    # Act
    described = Config.describe_store()
    # Assert
    assert "@" not in described


# ---------- mode selection ----------


def test_get_mode_honours_the_crossref_local_mode_variable(mode_env):
    # Arrange
    mode_env(CROSSREF_LOCAL_MODE="http")
    # Act
    mode = Config.get_mode()
    # Assert
    assert mode == "http"


def test_get_mode_accepts_store_as_a_spelling_of_db(mode_env):
    # Arrange
    mode_env(CROSSREF_LOCAL_MODE="store")
    # Act
    mode = Config.get_mode()
    # Assert
    assert mode == "db"


def test_scitex_scholar_variable_takes_priority_over_the_local_one(mode_env):
    # Arrange
    mode_env(CROSSREF_LOCAL_MODE="db", SCITEX_SCHOLAR_CROSSREF_MODE="http")
    # Act
    mode = Config.get_mode()
    # Assert
    assert mode == "http"


def test_config_set_mode_switches_to_http_mode(clean_config):
    # Arrange
    # Act
    Config.set_mode("http")
    # Assert
    assert Config.get_mode() == "http"


def test_config_set_mode_switches_to_db_mode(clean_config):
    # Arrange
    # Act
    Config.set_mode("db")
    # Assert
    assert Config.get_mode() == "db"


def test_config_set_mode_rejects_an_unknown_mode(clean_config):
    # Arrange
    # Act
    ctx = pytest.raises(ValueError)
    # Assert
    with ctx:
        Config.set_mode("telepathy")


def test_config_reset_returns_the_mode_to_auto(clean_config):
    # Arrange
    Config.set_mode("http")
    # Act
    Config.reset()
    # Assert
    assert Config._mode == "auto"


# ---------- API URL ----------


def test_config_set_api_url_stores_supplied_url(clean_config):
    # Arrange
    # Act
    Config.set_api_url("http://example.com:8333")
    # Assert
    assert Config.get_api_url() == "http://example.com:8333"


def test_config_set_api_url_strips_a_trailing_slash(clean_config):
    # Arrange
    # Act
    Config.set_api_url("http://example.com:8333/")
    # Assert
    assert Config.get_api_url() == "http://example.com:8333"


def test_config_set_api_url_implicitly_enables_http_mode(clean_config):
    # Arrange
    # Act
    Config.set_api_url("http://example.com:8333")
    # Assert
    assert Config.get_mode() == "http"


def test_config_reset_clears_the_cached_api_url(clean_config):
    # Arrange
    Config.set_api_url("http://example.com:8333")
    # Act
    Config.reset()
    # Assert
    assert Config._api_url is None


# ---------- defaults ----------


def test_default_api_urls_are_all_http_or_https_strings():
    # Arrange
    urls = DEFAULT_API_URLS
    # Act
    bad = [u for u in urls if not (isinstance(u, str) and u.startswith("http"))]
    # Assert
    assert bad == []


def test_default_api_url_is_the_first_of_the_candidates():
    # Arrange
    # Act
    first = DEFAULT_API_URLS[0]
    # Assert
    assert DEFAULT_API_URL == first


def test_default_port_follows_the_scitex_numbering_scheme():
    # Arrange — 31290 scitex-cloud, 31291 crossref-local, 31292 openalex.
    # Act
    port = DEFAULT_PORT
    # Assert
    assert port == 31291


def test_default_api_url_carries_the_default_port():
    # Arrange
    # Act
    url = DEFAULT_API_URL
    # Assert
    assert str(DEFAULT_PORT) in url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
