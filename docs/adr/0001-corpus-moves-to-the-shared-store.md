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

## Consequences, including the ones that hurt

**Search is a full scan.** The store primitive has no text search, no
filtered read, no aggregate and no ordering. `Store.rows()` returns every
record, so `_core/fts.py` matches in Python over the denormalised
`title` / `abstract` / `authors` fields. This is correct at any size and
fast only at small ones. Against a 167M-work corpus it is not viable.

**Counting is a full scan too.** The old `info()` stayed O(1) by reading
`MAX(rowid)`, which was a property of a rowid-addressed file rather than of
counting. That estimator has no replacement. `get_counts()` therefore reads
the cache or reports `counts_source: "unavailable"` — it never falls back
to a scan, because a fallback would turn every `info()` call and every
`/health` probe into a full-collection read.

**Every filtered lookup became a scan.** `get_citing` / `get_cited` were
two indexed lookups; they are now full reads of the citations collection.
`CitationNetwork` reads the edge list once and indexes it in memory rather
than asking per node, which is the only thing that keeps the traversal from
being quadratic.

**One public API field could not be reproduced.** `/api/stats/` returned
`tables` and `indices` arrays read out of `sqlite_master`. There is no
equivalent question to ask the primitive. See the endpoint for what is
returned instead.

### The gap this leaves in the primitive

These are not local problems to be worked around locally. They are missing
affordances in `scitex_dev.store`, and closing them belongs upstream:

1. **A filtered read.** Some way to ask for records matching a predicate
   without materialising the collection. Every consequence above follows
   from its absence.
2. **An aggregate.** At minimum a count. `len(store.rows())` is the only
   way to size a collection today.
3. **A text-search surface.** The engine underneath has full-text search;
   the primitive exposes no way to reach it.
4. **A bulk-ingest path.** `put()` is one optimistically-locked
   read-then-write per record with its own oplog entry. `batch()` amortises
   the commit and is worth ~9x, which is the difference between slow and
   impossible for a corpus this size — but it is still per-record work.

Until (1)–(3) exist, this package is correct and slow at corpus scale, and
that trade is taken deliberately rather than hidden. Until (4) exists, a
full corpus load is not attempted; the incremental REST-API path is.

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
