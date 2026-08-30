# ADR-0001 — The corpus moves to the fleet's shared store

- **Status:** accepted
- **Date:** 2026-08-30
- **Supersedes:** the implicit decision, never written down, that this
  package owned a database file on disk.

## Context

crossref-local was built as a thin facade over a single SQLite file: a
`works` table holding ~167M CrossRef records with their metadata as
compressed JSON blobs, a `works_fts` FTS5 virtual table joined on `rowid`,
a `citations` table of ~1.79B edges, two OpenAlex journal tables, and a
`db_stats` count cache. The file was ~1.5 TB and took about two weeks to
build from the CrossRef Public Data File using the pipeline under
`scripts/database/`.

The operator's standing directive is to eradicate SQLite from the SciTeX
fleet. `scitex-dev` 0.57.0 removed its SQLite backend, leaving exactly one
storage engine, and `docs/adr` is the only place in a fleet repository
where the name may still be written — which is why this file names it and
no other file does.

The reasons behind the fleet directive apply here and are not merely
stylistic. A database file has no concept of *who*: anyone who can open it
has every permission, and multi-user identity cannot be retrofitted onto a
file. Handing a collaborator a database file is sharing, not collaborating.
This package had already felt the shape of that problem — its answer to
"my machine has no copy of the 1.5 TB file" was an HTTP relay reachable
over an SSH tunnel, which is a second access-control system bolted on
outside the storage layer.

## Decision

The corpus moves to `scitex_dev.store` — one PostgreSQL per host, resolved
by `host_store()`, which is the single source of truth for DSN resolution.

The per-package database layer (`_core/db.py`) is **deleted rather than
reimplemented**. Consumers construct a `Store` and call `get` / `rows` /
`put` on the primitive directly. `_core/store.py` holds the `Schema`
declarations and the openers that hand out a bare `Store`; it exposes no
`execute`, no `fetchone`, no `fetchall`, and no query string. This is
deliberate: the previous wrapper was thin, and it still ended up with two
modules disagreeing about whether `works.metadata` was zlib-compressed
bytes or plain text, because a wrapper that passes SQL through cannot
enforce a shape. A declared `FieldKind.JSON` can, and does.

Five collections replace seven tables:

| was | is |
| --- | --- |
| `works` (+ `works_fts` joined on `rowid`) | `crossref_works` — searchable text is denormalised onto the record |
| `citations` | `crossref_citations` — the `(citing_doi, cited_doi)` pair is the identity, so re-ingest is idempotent |
| `journals_openalex` + `issn_lookup` | `crossref_journals` — alternate ISSNs are a list on the journal |
| `db_stats` | `crossref_corpus_stats` |
| `_metadata` | `crossref_sync_state` |

The multi-day bulk build pipeline is retired. Its output format no longer
exists, so those scripts were finished by construction, not merely old. The
one script that was still live — the differential updater — is now
`_core/ingest.py`, an ordinary module rather than a file loaded by path
that prepended `vendor/dois2sqlite` to `sys.path` to borrow that project's
row model. Both detours existed to agree with a file format; there is no
file and no bulk loader to agree with.

## Consequences

**Search is served by the store's own index.** `scitex_dev.store` 0.57.0
grew a read-by-criteria surface — `Store.search` / `count` / `tally`, a
`Query` type, and `Schema(text_search=...)` — landed in #764 and released
in #766. The works schema declares its searchable fields there, the store
builds a GIN index over exactly the expression the query compiler emits,
and matching, ordering and paging all happen in the database.

This ADR was first written against 0.57.0's predecessor, when the read door
offered only "one row by key" or "all of them", and it said search here had
to be a full scan in Python. **That is no longer true and the claim has been
removed rather than left standing** — an ADR that records a limitation which
has since been lifted is worse than one that records nothing, because the
next reader designs around a wall that is not there.

`_core/fts.py` keeps one small thing: it translates this package's published
`AND` / `OR` / `NOT` grammar into `websearch_to_tsquery` form. That is not a
workaround for a missing feature, it is a compatibility obligation — under
the `english` configuration those three words are stopwords, so passing them
through unchanged would not fail, it would silently invert `NOT`.

**Matching is by stemmed word, not by substring.** `editing` finds `edited`;
`neur` no longer finds `neural`. That matches what the retired engine's
index did, so it is a return to the documented behaviour.

**Counting happens in the database.** `count_works` and friends are
`Store.count(Query())`, so sizing a collection no longer materialises it in
this process — which on a 167M-work corpus was not a slow path but an
impossible one. It is still a scan inside the server, in the seconds, so
`get_counts()` remains cache-first and reports `counts_source:
"unavailable"` rather than putting that scan behind every `info()` call and
`/health` probe. An unmeasured count is reported as unknown, never guessed.

**Citation lookups are indexed.** `get_citing` / `get_cited` are
`Query().where(eq(...))` — the database returns only the matching edges.
`CitationNetwork` issues one bounded lookup per node per direction; an
earlier draft of this work read the whole edge collection once and indexed
it in memory, which was the right shape when the store could only be read
in full and is the wrong one now.

**One public API field could not be reproduced.** `/api/stats/` returned
`tables` and `indices` arrays read out of `sqlite_master`. There is no
equivalent question to ask the primitive. See the endpoint for what is
returned instead.

### The gap that remains

**Bulk ingest.** `put()` is one optimistically-locked read-then-write per
record with its own oplog entry. `batch()` amortises the commit and is worth
~9x, which is the difference between slow and impossible at this scale — but
it is still per-record work, and there is no path that streams a corpus in.
Until one exists a full 167M-work load is not attempted here; the
incremental REST-API path is what this package ships.

That is the whole of the outstanding list. The filtered read, the aggregate
and the text-search surface that the first draft of this ADR named as
missing all exist as of 0.57.0.

## Alternatives rejected

**Keep the file for the corpus and use the store for coordination.** This
is the arrangement the directive exists to end, and a partial exception is
the hardest kind to remove later — the remaining file would still have no
concept of who may read it.

**Write a local abstraction over the primitive so the call sites do not
change.** Explicitly rejected by the operator, and rightly: the deleted
wrapper is exactly what let a shape disagreement live in this package for
as long as it did.

**Reach around the primitive into its connection to issue SQL.** This would
restore the performance and discard every guarantee the primitive exists to
provide, while leaving the package's real requirement — a query surface —
undeclared, so nobody would ever build it.
