"""Store schemas for the CrossRef corpus, and the openers that hand them out.

This module holds DECLARATIONS, not an abstraction layer. There is no
``execute()``, no ``fetchone()``, no ``fetchall()`` and no query string
anywhere in this package: every consumer receives a bare
:class:`scitex_dev.store.Store` from one of the openers below and calls
``get`` / ``rows`` / ``put`` on the primitive itself.

Why the declarations live in one place
--------------------------------------
:class:`~scitex_dev.store.Schema` deliberately has no default
:class:`~scitex_dev.store.FieldPolicy` — every field must state its kind,
role, requiredness, merge rule and indexing explicitly, because a wrong
default merge rule loses data with nothing raised. That makes a schema
expensive to declare and disastrous to declare twice differently, so each
one is built exactly once here and imported by name. Re-declaring
``crossref_works`` at six call sites is how two of them end up disagreeing
about whether ``year`` is TEXT or INTEGER.

Why the openers are thread-local
--------------------------------
Constructing a ``Store`` opens a connection and takes the dialect's schema
lock to check its objects exist. The async layer (``crossref_local._aio``)
runs the synchronous read path on a thread-pool worker, so a process-wide
singleton would share one connection across threads. One store per thread
per schema is the same shape the package used before, for the same reason.

Storage note
------------
``works.metadata`` is a ``FieldKind.JSON`` field: the primitive serialises
it on write and returns a ``dict`` on read. Nothing compresses or decodes
it by hand, which removes the previous zlib-BLOB-or-plain-text ambiguity
that two modules disagreed about.
"""

from __future__ import annotations

import socket as _socket
import threading as _threading

from scitex_dev.store import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
    Store,
    StoreTarget,
    WriterPolicy,
    host_store,
)

__all__ = [
    "CITATIONS",
    "CORPUS_STATS",
    "JOURNALS",
    "SYNC_STATE",
    "WORKS",
    "citations_store",
    "close_stores",
    "corpus_stats_store",
    "journals_store",
    "node_id",
    "sync_state_store",
    "target_for",
    "works_store",
]

#: The package slot every store target is namespaced under.
PKG = "crossref_local"

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
# Written out in full rather than through a local helper with defaults.
# A helper that supplies a default merge rule would reintroduce exactly the
# silent-data-loss hazard FieldPolicy exists to refuse.

#: One CrossRef work, keyed by DOI.
#:
#: ``title`` / ``abstract`` / ``authors`` are denormalised out of
#: ``metadata`` because they are what search reads. They replace the former
#: ``works_fts`` virtual table, which had no key of its own and was joined
#: on ``rowid`` — a coupling with no analogue outside a file-backed engine.
WORKS: Schema = Schema.build(
    "crossref_works",
    {
        "doi": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
        "metadata": FieldPolicy(
            kind=FieldKind.JSON,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "title": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "abstract": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "authors": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "container_title": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "issn": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "year": FieldPolicy(
            kind=FieldKind.INTEGER,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "work_type": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "referenced_by_count": FieldPolicy(
            kind=FieldKind.INTEGER,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "reference_count": FieldPolicy(
            kind=FieldKind.INTEGER,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
    },
    # The fields a full-text query searches, declared ONCE here because the
    # store builds its text index from this list and the query compiler
    # builds its match expression from the same list. An index that differs
    # from its query by one character is simply never used, the planner says
    # nothing about it, and the only symptom is that search got slow.
    #
    # This is what replaces the retired engine's separate full-text table,
    # and it is a strictly better arrangement: that table was joined on a
    # row identifier and could drift out of sync with the works it indexed,
    # whereas these are columns of the record itself.
    text_search=("title", "abstract", "authors", "container_title"),
    # `english` stems and drops stopwords, which is what a literature search
    # wants: "editing" should find "edited". The cost is that a stopword
    # cannot be searched for on its own, which is why the grammar in
    # `_core/fts.py` translates its operators rather than passing them
    # through as words — see `_websearch_query` there.
    text_config="english",
)

#: One directed citation edge. The pair is the identity, so re-ingesting the
#: same edge is idempotent rather than a duplicate row.
CITATIONS: Schema = Schema.build(
    "crossref_citations",
    {
        "citing_doi": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
        "cited_doi": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
        "citing_year": FieldPolicy(
            kind=FieldKind.INTEGER,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
    },
)

#: OpenAlex journal metadata, keyed by ISSN-L. Replaces both
#: ``journals_openalex`` and the ``issn_lookup`` join table: alternate ISSNs
#: live in the ``issns`` list on the journal itself, so there is nothing to
#: join and no second table whose presence had to be probed at runtime.
JOURNALS: Schema = Schema.build(
    "crossref_journals",
    {
        "issn_l": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
        "name": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "name_lower": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "issns": FieldPolicy(
            kind=FieldKind.JSON,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.UNION,
            indexed=False,
        ),
        "publisher": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "works_count": FieldPolicy(
            kind=FieldKind.INTEGER,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "two_year_mean_citedness": FieldPolicy(
            kind=FieldKind.REAL,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "h_index": FieldPolicy(
            kind=FieldKind.INTEGER,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "is_oa": FieldPolicy(
            kind=FieldKind.BOOL,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
    },
)

#: The exact-count cache. ``computed_at`` records when the count was taken;
#: an ``info()`` call reads this and never counts the corpus itself.
CORPUS_STATS: Schema = Schema.build(
    "crossref_corpus_stats",
    {
        "collection": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
        "row_count": FieldPolicy(
            kind=FieldKind.INTEGER,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "computed_at": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
    },
)

#: Differential-update bookkeeping — the successor to the ``_metadata``
#: key/value table the old ingest script kept beside the corpus.
SYNC_STATE: Schema = Schema.build(
    "crossref_sync_state",
    {
        "key": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
        "value": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
    },
)

_SCHEMAS = {
    "works": WORKS,
    "citations": CITATIONS,
    "journals": JOURNALS,
    "corpus_stats": CORPUS_STATS,
    "sync_state": SYNC_STATE,
}

# ---------------------------------------------------------------------------
# Openers
# ---------------------------------------------------------------------------

_local = _threading.local()


def node_id() -> str:
    """This node's identity for the oplog and the hybrid-logical clock.

    The hostname, which is what the primitive asks for when one process per
    host writes. Deliberately not read from a DSN or a config file: the node
    id names WHO WROTE, and taking it from the connection string would make
    two hosts sharing a store indistinguishable in their own history.
    """
    return _socket.gethostname()


def target_for(name: str) -> StoreTarget:
    """Resolve the store target for one collection.

    :func:`~scitex_dev.store.host_store` is the single source of truth for
    DSN resolution — it honours ``SCITEX_STORE_DSN`` and otherwise reaches
    this host's own PostgreSQL. No DSN is constructed here, and none is
    hardcoded anywhere in this package or its tests.
    """
    return host_store(pkg=PKG, name=name)


def _open(name: str) -> Store:
    cache = getattr(_local, "stores", None)
    if cache is None:
        cache = {}
        _local.stores = cache
    store = cache.get(name)
    if store is None:
        store = Store(
            target_for(name),
            _SCHEMAS[name],
            node=node_id(),
            # MULTI_WRITER: corpus rows have no meaningful owner, and an
            # ingest run on one host must be able to refresh a row another
            # host wrote. SINGLE_WRITER would refuse exactly that.
            writer_policy=WriterPolicy.MULTI_WRITER,
        )
        cache[name] = store
    return store


def works_store() -> Store:
    """The works collection, as a bare :class:`~scitex_dev.store.Store`."""
    return _open("works")


def citations_store() -> Store:
    """The citation-edge collection."""
    return _open("citations")


def journals_store() -> Store:
    """The OpenAlex journal collection."""
    return _open("journals")


def corpus_stats_store() -> Store:
    """The exact-count cache."""
    return _open("corpus_stats")


def sync_state_store() -> Store:
    """Differential-update bookkeeping."""
    return _open("sync_state")


def close_stores() -> None:
    """Close every store this thread opened.

    Nothing is deleted and nothing is reset — the primitive has no delete
    verb. This only releases connections, and the next opener call builds a
    fresh one.
    """
    cache = getattr(_local, "stores", None)
    if not cache:
        return
    for store in cache.values():
        try:
            store.close()
        except Exception:
            # A connection already dropped by the server is not an error the
            # caller can act on, and raising here would mask whatever the
            # caller was actually shutting down for.
            pass
    _local.stores = {}

# EOF
