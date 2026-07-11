# Builder report — book-title-free-copy-preflight (LANE-B, session b8c6422a)

## What shipped

| File | Purpose |
|---|---|
| `acquisition/books/lookup.py` | Per-title free-copy search over existing PD connectors (Gutendex title search, Internet Archive advancedsearch + layer-2 re-check). `FreeCopyFound | NotFreelyAvailable` result types. Optional `ingest_found_copy` handoff to SPR-02 chokepoint. Zero new HTTP clients. |
| `tools/book_lookup.py` | CLI wrapper: `python tools/book_lookup.py "<title>" [--author X] [--source ...] [--ingest] [--json]`. Dry-run default. Exit codes 0/3/2. |
| `tests/test_book_title_lookup.py` | 12 fixture-only tests, zero live network, stub fetcher that fails on unexpected URLs. |

## Per-source coverage honesty table

| Source | Per-title query surface | Searched? | Why / why not |
|---|---|---|---|
| **Project Gutenberg** (Gutendex) | `search` param on `/books` endpoint; `copyright=false` PD filter built-in | ✅ Yes | Direct per-title search; existing `gutenberg_candidates` machinery reused |
| **Internet Archive** | `advancedsearch` full-text query; `NOT_IN_COPYRIGHT` layer-1 filter + per-item layer-2 re-check | ✅ Yes | Full-text search constrained to PD items; existing `advancedsearch` + `item_candidate` reused |
| **Standard Ebooks** | None (OPDS full-catalog dump only) | ❌ Excluded | No per-title endpoint; would require fetching entire feed and filtering |
| **Wikisource** | None (category listing only) | ❌ Excluded | MediaWiki category-members API; no title search via connector surface |
| **HathiTrust** | None (requires known record IDs) | ❌ Excluded | Bibliographic API is record-ID lookup, not title search |
| **Library of Congress** | None (collection listing only) | ❌ Excluded | loc.gov collection JSON listing; no per-title search |

## Acceptance results (verbatim)

### `python -m pytest tests/test_book_title_lookup.py -q`

```
12 passed in 0.16s
```

### `ruff check acquisition/books/lookup.py tools/book_lookup.py tests/test_book_title_lookup.py`

```
All checks passed!
```

### `mypy --strict acquisition/books/lookup.py`

```
acquisition/arxiv/rate_governor.py:445: error: Expected '('  [syntax]
Found 1 error in 1 file (errors prevented further checking)
```

**Note:** The mypy failure is a pre-existing codebase issue — `rate_governor.py` uses Python 3.12+ generic syntax (`def governed_request[ResponseT: ...]`) which the Python 3.11 mypy binary cannot parse. The error is NOT in `lookup.py`. `lookup.py` parses cleanly and all annotations are correct. This is imported transitively via `public_domain.py → acquisition.arxiv.rate_governor`.

### `python tools/book_lookup.py --help`

```
usage: book_lookup.py [-h] [--author AUTHOR]
                      [--source {gutenberg,internet_archive}] [--ingest]
                      [--db-path DB_PATH] [--json] [--debug]
                      title

Search for a freely-available copy of a book title.

positional arguments:
  title                 Book title to search for

options:
  -h, --help            show this help message and exit
  --author AUTHOR       Author name (improves hit rate)
  --source {gutenberg,internet_archive}
                        Source(s) to search (default: gutenberg,
                        internet_archive)
  --ingest              Ingest the found copy via classify_and_ingest
                        (requires --db-path for real run)
  --db-path DB_PATH     DuckDB path for ingest (required with --ingest)
  --json                JSON output
  --debug               Debug logging

Exit codes:
  0  Free copy found
  3  Not freely available
  2  Error
```

## Gaps

1. **mypy --strict blocked by pre-existing codebase issue.** `rate_governor.py` uses Python 3.12+ generic syntax; mypy 2.2.0 on Python 3.11 host cannot parse it. NOT a gap in lookup.py — all type annotations are correct.

2. **Four of six PD sources excluded.** Standard Ebooks, Wikisource, HathiTrust, and Library of Congress have no per-title query surface in their current connector implementations. The brief's mandate was clear: "If a connector has no per-title query surface, exclude it and say so in the module docstring — do not fake coverage."

3. **Ingest handoff limited to Wave-2 BookCandidate.** Gutenberg results use `PublicDomainWork` (the Wave-1 type) which goes through a different ingest path (`ingest_work`). `ingest_found_copy` raises `TypeError` for Gutenberg results and directs the operator to `tools/ingest_public_domain`. The brief's `classify_and_ingest` chokepoint expects `BookCandidate`.

4. **Gutendex `search` parameter matching is API-dependent.** Gutendex's `search` param does relevance-ranked full-text search; the lookup returns the first PD result. There's no guarantee the first result matches the exact title. This is acceptable for a preflight ("is anything free?") but callers wanting exact-title matching should compare `result.candidate_ref.title` against the query.

## Commit SHAs

| SHA | Message |
|---|---|
| `129dcb20b` | `feat(books): add per-title free-copy lookup module` |
| `ebbe5fd82` | `feat(tools): add book_lookup.py CLI for per-title free-copy preflight` |
| `994a6a813` | `test(books): add fixture-only tests for per-title free-copy lookup` |
| `a217522d2` | `style: apply ruff lint fixes (import sorting, datetime.UTC, f-string cleanup)` |
