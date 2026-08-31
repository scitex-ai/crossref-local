"""Pytest configuration and fixtures for crossref_local tests.

BACKING STORE
-------------
The corpus lives in the fleet's shared store primitive, so there is no
fixture database FILE any more and nothing here looks for one. What the
suite needs instead is a *writable* PostgreSQL it may create and destroy a
schema on.

Two rules shape everything below:

1. **Never write to the production store.** ``host_store()`` resolves
   ``SCITEX_STORE_DSN`` and, given no schema of its own, a ``Store`` would
   create ``crossref_works`` and friends in whatever database that names.
   So the session opens ONE throwaway schema
   (:func:`scitex_dev.store.testing.ephemeral_schema`) and points
   ``SCITEX_STORE_DSN`` at it for the whole run. Every store the package
   opens through its own resolution path therefore lands inside that
   schema, and the schema is dropped when the run ends.
2. **No writable PostgreSQL is a SKIP, not a failure.**
   :func:`~scitex_dev.store.testing.writable_dsn` raises ``RuntimeError``
   when neither a configured writable cluster nor ``initdb`` is available,
   which is the normal state on the self-hosted CI runner. That is an
   environment fact, not a defect in this package.

The throwaway schema is SEEDED with a small corpus (built through the
package's own :func:`crossref_local._core.ingest.work_values` normaliser,
so the fixture records have exactly the shape ingest writes). That seed is
the direct replacement for the deleted ``fixtures/test_crossref.db``: the
corpus-shaped tests query it the same way they queried that file.
"""

import contextlib
import os
import sysconfig
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Subprocess coverage wiring (TODO §0). Force-set (NOT setdefault — that is a
# silent no-op when the env var is empty) so child Python interpreters spawned
# by tests (subprocess.run, click CliRunner via fresh interpreter, etc.)
# inherit coverage. See:
#   ~/proj/scitex-dev/src/scitex_dev/_skills/general/
#     05_development_06_subprocess-coverage.md
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
os.environ["COVERAGE_PROCESS_START"] = str(_REPO_ROOT / "pyproject.toml")
os.environ["COVERAGE_FILE"] = str(_REPO_ROOT / ".coverage")

# Idempotent .pth shim: ensures `coverage.process_startup()` runs on
# every child interpreter import.
try:
    _SITE = Path(sysconfig.get_paths()["purelib"])
    _PTH = _SITE / "coverage_subprocess.pth"
    _SHIM = "import coverage; coverage.process_startup()"
    if not _PTH.exists() or _PTH.read_text().strip() != _SHIM:
        _PTH.write_text(_SHIM + "\n")
except Exception:
    # Best-effort: failure here only loses subprocess coverage; do not
    # break the test run.
    pass

#: The one knob that decides which store the package opens. Set to the
#: session's throwaway schema below; restored when the run ends.
STORE_DSN_ENV = "SCITEX_STORE_DSN"

# ---------------------------------------------------------------------------
# Module allowlist — tests that must NEVER be blanket-skipped
# ---------------------------------------------------------------------------
# The old list swept up modules that touch no storage at all and skipped
# them whenever the fixture database was missing, which cost real coverage
# for no reason. Each entry below states why it is safe.
_STORE_OPTIONAL_TEST_MODULES = frozenset(
    {
        # -- genuinely storage-free ------------------------------------
        # Pure dataclass construction / serialisation.
        "test_models",
        # Drives a real localhost HTTP server started by the test itself;
        # the client never opens a store.
        "test_remote",
        # On-disk JSON cache under tmp_path.
        "test_cache",
        # JobQueue reads and writes JSON files under tmp_path.
        "test_jobs",
        # Renders shell-completion scripts from the click command tree.
        "test_cli_completion",
        # Mode selection and API-URL resolution: resolution only, never a
        # connection.
        "test_config",
        # Asserts the MCP tool surface exists; no records are read.
        "test_mcp_server",
        # Imports sibling packages to check they are installed.
        "test_cross_package_imports",
        # Reads the repo's own source layout.
        "test_audit",
        "test_paths_runtime",
        # Lints the bundled skill markdown.
        "test_skills_quality",
        # `py_compile` smoke over examples/*.py — never executes them.
        "test_01_quickstart",
        "test_05_abstract_coverage",
        "test_compose_readme",
        # -- store-touching but SELF-PROVISIONING ----------------------
        # These open their own throwaway schema through the `store_env`
        # fixture, which skips itself when no writable PostgreSQL exists.
        "test_store",
        "test_stats",
        "test_fts",
        "test_cli_stats",
        "test_cli_update",
    }
)

# Set in `pytest_configure`; consumed by `pytest_collection_modifyitems`.
_DB_AVAILABLE = False
_STORE_UNAVAILABLE = False

#: Set once, by `pytest_configure`, when NO writable PostgreSQL could be
#: provisioned for this session. `store_env` consults it instead of probing
#: again per test.
#:
#: WHY THIS EXISTS. Widening the exception below stopped a `pg_ctl` hang from
#: killing the run, but left every `store_env` test to rediscover the same
#: hang for itself. There are 36 of them and the timeout is 120s, so the
#: suite went from crashing in two minutes to grinding for over an hour —
#: still reported as "in progress", which is the failure mode that looks
#: like patience. The probe's ANSWER is a property of the session, not of
#: each test, so it is taken once.

#: Holds the session's writable-DSN and ephemeral-schema contexts open for
#: the whole run; unwound in `pytest_unconfigure`.
_SESSION_STACK = contextlib.ExitStack()


def _check_remote_api():
    """Check if remote API is available."""
    try:
        import urllib.request

        req = urllib.request.Request("http://localhost:3333/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The seed corpus
# ---------------------------------------------------------------------------
# CrossRef-shaped items, normalised by the package's own `work_values`. Every
# record mentions "neuroscience" (and therefore "science", by substring) so
# the historic paging assertions have enough hits to page through; the
# remaining terms are spread across the corpus so a query still discriminates
# — a fixture in which every query matched every record would let a broken
# predicate pass.
_SEED_AUTHORS = [{"given": "Ada", "family": "Lovelace"}]

_SEED_TOPICS = (
    ("Sharp wave ripples in the hippocampus", "cancer medicine biology genetics CRISPR"),
    ("Cortical microcircuits under anaesthesia", "cancer medicine biology genetics CRISPR"),
    ("Dendritic computation in pyramidal cells", "cancer medicine biology genetics CRISPR"),
    ("Population coding of spatial context", "cancer medicine biology genetics CRISPR"),
    ("Synaptic plasticity and memory consolidation", "cancer medicine biology genetics CRISPR"),
    ("Oscillatory coupling across cortical areas", "cancer medicine biology genetics CRISPR"),
    ("Quantum effects in biological photoreceptors", "physics chemistry quantum machine learning"),
    ("Spectroscopy of neural tissue", "physics chemistry quantum machine learning"),
    ("Statistical models of spike trains", "physics chemistry quantum machine learning"),
    ("Optical imaging of cortical dynamics", "physics chemistry quantum machine learning"),
)

#: A known DOI the historic suite asks for by name.
SAMPLE_DOI = "10.1126/science.aax0758"

_SEED_DOIS = (SAMPLE_DOI,) + tuple(
    f"10.1000/crossref.local.seed.{index:03d}" for index in range(1, 10)
)


def _seed_items():
    """Build the CrossRef-shaped items the throwaway store is seeded with."""
    items = []
    for index, (doi, (title, terms)) in enumerate(zip(_SEED_DOIS, _SEED_TOPICS)):
        items.append(
            {
                "DOI": doi,
                "type": "journal-article",
                "title": [title],
                "abstract": (
                    f"A neuroscience test record about {terms}. "
                    "Seeded so the suite can query a real store."
                ),
                "author": _SEED_AUTHORS,
                "container-title": ["Journal of Test Neuroscience"],
                "ISSN": ["1234-5678"],
                "published": {"date-parts": [[2020 + index % 5]]},
                "is-referenced-by-count": index,
                "reference": [{"DOI": _SEED_DOIS[0]}] if index else [],
            }
        )
    return items


def _seed_store():
    """Write the fixture corpus into the session's throwaway schema.

    Uses the package's real ingest normaliser and the real openers, so the
    seeded records are byte-for-byte what an ingest run would write. Returns
    ``True`` when the corpus is in place.
    """
    from scitex_dev.store import ANY_REVISION

    from crossref_local._core.ingest import upsert_work
    from crossref_local._core.stats import refresh_stats
    from crossref_local._core.store import (
        citations_store,
        close_stores,
        works_store,
    )

    close_stores()
    works = works_store()
    for item in _seed_items():
        upsert_work(works, item)

    edges = citations_store()
    for doi in _SEED_DOIS[1:4]:
        edges.put(
            {"citing_doi": doi, "cited_doi": SAMPLE_DOI, "citing_year": 2023},
            expected_revision=ANY_REVISION,
        )
    edges.put(
        {"citing_doi": SAMPLE_DOI, "cited_doi": _SEED_DOIS[5], "citing_year": 2023},
        expected_revision=ANY_REVISION,
    )

    # Exact counts, so info() / /info report counts_source == "exact"
    # without ever counting on the read path.
    refresh_stats()
    return True


def pytest_configure(config):
    """Resolve the backing store: throwaway PostgreSQL schema > remote API.

    Resolution order:

    1. A writable PostgreSQL (``SCITEX_STORE_DSN`` when it names one, else a
       private cluster started by ``initdb``). A throwaway schema is created
       on it, ``SCITEX_STORE_DSN`` is repointed at that schema, and a small
       corpus is seeded into it. Nothing outside the schema is touched.
    2. Remote relay/API reachable at the configured URL (when the package is
       in ``http`` mode pointing at a separate host; respects
       ``CROSSREF_LOCAL_MODE=http``).
    3. Nothing available -> corpus-dependent tests skip; storage-free and
       self-provisioning modules still run.
    """
    global _DB_AVAILABLE, _STORE_UNAVAILABLE

    try:
        from scitex_dev.store import testing
    except ImportError as exc:
        print(f"\nscitex_dev.store.testing unavailable ({exc}) — store tests skip")
        testing = None

    if testing is not None:
        try:
            dsn = _SESSION_STACK.enter_context(testing.writable_dsn())
        except Exception as exc:  # noqa: BLE001 - see below; never abort here
            # DELIBERATELY BROADER THAN RuntimeError, and the difference took
            # the whole suite down once. `writable_dsn` documents RuntimeError
            # for "no route available", but its private-cluster fallback shells
            # out to `initdb`/`pg_ctl` and can therefore also raise
            # `subprocess.TimeoutExpired` or `CalledProcessError` — neither of
            # which is a RuntimeError. Measured on the CI runner 2026-08-30:
            # PostgreSQL 16 IS installed there, so the fallback was taken
            # rather than skipped, `pg_ctl ... start` hung, and the timeout
            # escaped `pytest_configure` as an INTERNALERROR with exit code 3.
            # Not one test failed; the session simply died before running.
            #
            # Provisioning a store for the suite is a PROBE, not the thing
            # under test, so every way it can fail is "no store — skip", never
            # "abort the run". The reason is printed so a real outage is still
            # diagnosable rather than silently absorbed.
            print(f"\nNo writable PostgreSQL for tests: {exc!r}")
            _STORE_UNAVAILABLE = True
        else:
            scoped = _SESSION_STACK.enter_context(
                testing.ephemeral_schema(dsn, prefix="crossref_session")
            )
            previous = os.environ.get(STORE_DSN_ENV)
            _SESSION_STACK.callback(_restore_store_dsn, previous)
            os.environ[STORE_DSN_ENV] = scoped
            try:
                _DB_AVAILABLE = _seed_store()
            except Exception as exc:  # noqa: BLE001 - report, never abort
                print(f"\nCould not seed the throwaway store ({exc!r})")
            else:
                print("\nUsing a throwaway PostgreSQL schema seeded for tests")
                return

    # No usable store. Respect MODE=http: if a remote host is reachable via
    # a forwarded relay port (e.g. SSH `LocalForward 31291`), tests can drive
    # the package through its HTTP path instead of skipping.
    mode = os.environ.get("CROSSREF_LOCAL_MODE", "").lower()
    if mode == "http" and _check_remote_api():
        _DB_AVAILABLE = True
        print("\nNo local store; using remote relay via SSH tunnel (MODE=http)")
        return

    # Last-resort heuristic: remote API at default URL responds.
    if _check_remote_api():
        os.environ["CROSSREF_LOCAL_MODE"] = "http"
        _DB_AVAILABLE = True
        print("\nNo local store; default API URL responds — running via HTTP")
        return

    if not _DB_AVAILABLE:
        print("\nNo backing store — corpus-dependent tests will be skipped")


def _restore_store_dsn(previous):
    """Put ``SCITEX_STORE_DSN`` back the way the session found it."""
    if previous is None:
        os.environ.pop(STORE_DSN_ENV, None)
    else:
        os.environ[STORE_DSN_ENV] = previous


def pytest_unconfigure(config):
    """Drop the throwaway schema (and any private cluster) after the run."""
    with contextlib.suppress(Exception):
        from crossref_local._core.store import close_stores

        close_stores()
    _SESSION_STACK.close()


def pytest_collection_modifyitems(config, items):
    """Auto-skip corpus-dependent tests when no backing store is available.

    Without this hook the ~130 store-touching tests fail with a connection
    error at runtime. With it they SKIP cleanly, so an environment with no
    writable PostgreSQL (the self-hosted CI runner) gets a green run on the
    storage-free and self-provisioning subset.
    """
    if _DB_AVAILABLE:
        return
    skip_no_store = pytest.mark.skip(
        reason="no writable PostgreSQL for the corpus (storage-free tests still run)"
    )
    for item in items:
        # `item.module.__name__` is e.g. "tests.crossref_local.test_aio"
        mod_short = item.module.__name__.rsplit(".", 1)[-1]
        if mod_short not in _STORE_OPTIONAL_TEST_MODULES:
            item.add_marker(skip_no_store)


@pytest.fixture
def store_env():
    """Point the package's own store resolution at a throwaway schema.

    Not an injection and not a mock: setting ``SCITEX_STORE_DSN`` is the
    documented way to choose a store, so the package's REAL resolution path
    runs and opens a REAL PostgreSQL — one whose schema is dropped when the
    test ends. The env var is restored explicitly afterwards.

    ``close_stores()`` brackets the body because the openers cache one store
    per thread: without it, this test would reuse the store the previous
    test opened against a different DSN.
    """
    testing = pytest.importorskip("scitex_dev.store.testing")
    if _STORE_UNAVAILABLE:
        # The session already established there is no writable PostgreSQL.
        # Re-probing would pay the same multi-minute timeout per test for an
        # answer that cannot have changed.
        pytest.skip("no writable PostgreSQL for store tests (probed once at session start)")
    previous = os.environ.get(STORE_DSN_ENV)
    try:
        with contextlib.ExitStack() as stack:
            try:
                dsn = stack.enter_context(testing.writable_dsn())
            except Exception as exc:  # noqa: BLE001 - a probe, not the subject
                # Same reasoning as `pytest_configure`: the private-cluster
                # fallback can fail with a subprocess error rather than the
                # documented RuntimeError, and a store this fixture cannot
                # provision is a skip, not an error in what is being tested.
                pytest.skip(f"no writable PostgreSQL for store tests: {exc!r}")
            scoped = stack.enter_context(
                testing.ephemeral_schema(dsn, prefix="crossref")
            )
            os.environ[STORE_DSN_ENV] = scoped
            from crossref_local._core.store import close_stores

            close_stores()
            yield scoped
            close_stores()
    finally:
        _restore_store_dsn(previous)


@pytest.fixture
def sample_doi():
    """Return a known DOI from the seeded corpus."""
    return SAMPLE_DOI
