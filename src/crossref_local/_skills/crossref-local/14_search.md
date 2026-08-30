---
description: |
  [TOPIC] Search
  [DETAILS] Full-text search across titles, abstracts, authors and container titles. Matched in Python over the works collection — one full scan per query.
tags: [crossref-local-search, crossref-local]
package: crossref-local
skill: search
---


# Search

Full-text search across titles, abstracts, authors and container titles.

> **Read this before using `search()` or `count()` at scale.** There is no
> search index. The store primitive has no text-search surface, no filtered
> read and no aggregate, so matching happens in Python over every record in
> the works collection: **one full scan of the collection per query**, with
> the matched slice held in memory. That is correct at any size and
> acceptable only at small ones — against the full ~167M-work corpus it is
> not viable. This is a real regression against the previous file-backed
> engine. The fix is a query surface on the store primitive, which does not
> exist yet; see `crossref_local._core.fts` and the ADR under `docs/adr/`.
>
> DOI lookups (`get()`, `get_many()`, `exists()`) are unaffected — they are
> keyed reads and stay cheap at any size.

## Signatures

```python
search(
    query: str,
    limit: int = 10,
    offset: int = 0,
    with_if: bool = False,
) -> SearchResult

count(query: str) -> int

exists(doi: str) -> bool
```

## Parameters

### `search()`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | required | Search query (grammar below) |
| `limit` | int | 10 | Max results to return |
| `offset` | int | 0 | Skip first N results (pagination) |
| `with_if` | bool | False | Include OpenAlex impact factor data |

Results are ordered by DOI. The ordering is imposed by crossref-local, not
by the store: `Store.rows()` makes no ordering promise, so paginating on its
natural order would let the same offset return different works between
calls.

### `count()`

Returns the total number of matching works without building `Work` objects.
It is cheaper than `search()` only in object construction — **the scan is
the same**, because the store cannot count a subset.

### `exists()`

Returns `True` if the DOI is present. A keyed read, not a scan.

## Query Syntax

| Syntax | Meaning | Example |
|--------|---------|---------|
| `word` | Term is a substring of the work's text | `CRISPR` |
| `"exact phrase"` | Phrase as a single substring | `"sharp wave ripples"` |
| `word1 word2` | Both required (`AND` is the default join) | `neural network` |
| `word1 AND word2` | Both required | `neural AND network` |
| `word1 OR word2` | Either | `hippocampus OR cortex` |
| `NOT word` | Exclude | `seizure NOT epilepsy` |

Matching is case-insensitive substring matching over `title`, `abstract`,
`authors` and `container_title`. Consequences worth knowing:

- **No prefix operator.** `neuro*` matches the literal `neuro*` and finds
  nothing. A bare `neuro` already matches `neuroscience`.
- **No word boundaries.** `cat` matches `catalysis`. Quote a phrase to
  constrain it, or add a discriminating term.
- **`NEAR` is accepted and treated as `AND`.** Proximity needs positional
  information this store does not keep; the match is widened rather than
  returning proximity-ordered nonsense. The result count tells you.
- **An empty query matches nothing**, deliberately — returning every work
  for `""` would turn missing caller input into a full-corpus read.

## Examples

```python
import crossref_local as crl

# Basic search
results = crl.search("hippocampal sharp wave ripples")
print(f"Found {results.total:,} matches in {results.elapsed_ms:.1f}ms")
for work in results:
    print(f"  {work.title} ({work.year}) DOI:{work.doi}")

# Paginate — note each call re-scans the collection
page1 = crl.search("machine learning", limit=20, offset=0)
page2 = crl.search("machine learning", limit=20, offset=20)

# Count only
n = crl.count("CRISPR AND cancer")
print(f"{n:,} papers on CRISPR and cancer")

# Check existence — keyed read, cheap
if crl.exists("10.1038/nature12373"):
    print("DOI is in the corpus")

# Boolean operators
results = crl.search('"deep learning" AND brain NOT review', limit=50)

# With impact factor
results = crl.search("epilepsy seizure prediction", with_if=True)
for work in results:
    if work.impact_factor:
        print(f"IF {work.impact_factor:.1f}: {work.title}")
```

## `@supports_return_as` Decorator

All search functions are decorated with `@supports_return_as` from
`scitex_dev`, enabling alternate return formats:

```python
# Return as pandas DataFrame
df = crl.search("CRISPR", limit=100, return_as="dataframe")

# Return as JSON string
json_str = crl.count("deep learning", return_as="json")
```

## Performance Notes

- Search covers titles, abstracts, authors and container titles.
- Latency scales with the size of the works collection, not with the number
  of matches: `limit` and `offset` cap what is returned, never what is read.
- `count()` avoids building `Work` objects but performs the same scan.
- `exists()` is a direct keyed lookup — the fastest single-DOI check.
- Pagination re-scans. To page through a large result set, call
  `crossref_local._core.fts.matches()` once and slice it yourself.
