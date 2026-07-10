## Sprint SPR-06 — Handoff

### Status
DONE

### Files touched
- `substrate/corpus_contract/__init__.py:1-31` — package init, public API exports (CorpusAdapter, CorpusHit, CorpusDocument, CorpusMiss, Provenance, FetchResult)
- `substrate/corpus_contract/protocol.py:1-130` — typing.Protocol (CorpusAdapter) with search/fetch; CorpusHit (id, score, snippet); CorpusDocument (content, provenance); CorpusMiss (typed, not bare KeyError); Provenance (source_kind, origin_ref, retrieved_at)
- `substrate/corpus_contract/adapters/__init__.py:1-1` — subpackage marker
- `substrate/corpus_contract/adapters/twin_notes.py:1-124` — TwinNotesCorpusAdapter over TwinNoteReader protocol; honest substring matching; fields mirrored from real store (note_id, asset_id, kind, text, source_spawn_id, investigation_id)
- `substrate/corpus_contract/adapters/hosted_docs.py:1-124` — HostedDocsCorpusAdapter over HostedDocReader protocol; honest substring matching; fields mirrored from real store (document_id, owner_id, book_id, content_hash, title, license_class, body_text, source_format, receipt_id, view_format)
- `substrate/corpus_contract/conformance.py:1-179` — reusable conformance kit: 7 assert helpers + BrokenProvenanceAdapter red-proof
- `tests/test_corpus_contract.py:1-242` — 17 tests: 7 twin-notes, 7 hosted-docs, 3 broken-adapter red-proof
- `substrate/corpus_contract/WIRING.md:1-64` — frozen-file wiring needs + doctrine invariants

### Milestones
- [x] M1: Protocol + document type — VERIFIED (mypy --strict green, protocol conformance type tests in protocol.py)
- [x] M2: Reference adapter: twin notes — VERIFIED (passes conformance kit, zero writes interface-proven via TwinNoteReader protocol)
- [x] M3: Reference adapter: hosted documents — VERIFIED (passes same conformance kit unchanged)
- [x] M4: Conformance kit + tests + WIRING.md — VERIFIED (kit runs against both adapters, broken-adapter red-proof included)

### Verification gate results
- pytest: pass (17 passed in 0.23s)
- mypy strict: pass (Success: no issues found in 6 source files)
- ruff: pass (All checks passed!)
- seam purity: pass (all changes within owned files: substrate/corpus_contract/* + tests/test_corpus_contract.py)

### WIRING.md entries added (frozen-file needs documented, not edited)
- `substrate/engagement_spine/__init__.py` → re-export TwinNotesCorpusAdapter (SPR-05 consumes twin notes through the protocol)
- `substrate/marketplace_host/__init__.py` → re-export HostedDocsCorpusAdapter (SPR-07/08 acquisition outputs become corpora)
- `runtime/research_loop.py` (or equivalent) → accept CorpusAdapter protocol, not concrete store handles

### Decisions made mid-flight
- **Decision:** Accept a reader protocol (TwinNoteReader / HostedDocReader) rather than the full store (EngagementStore / HostStore). **Why:** the spec demands zero writes be interface-proven, not conventional. A reader protocol with no write method makes read-only structural. **What would reverse it:** if a future adapter needs write-through caching (unlikely — doctrine I-8 is binding).
- **Decision:** Search uses simple substring matching, not TF-IDF or embeddings. **Why:** the spec says "honest lexical matching" and "no embedding dependency." The conformance kit's retrieval assertion (fixture doc with exact query phrase must rank first) works with substring. **What would reverse it:** if recall measurably degrades on real corpora — but that's the store's concern, not the contract's.
- **Decision:** `FetchResult = CorpusDocument | CorpusMiss` (union type) rather than raising exceptions. **Why:** the spec says "fetch of an unknown id has one documented behavior (typed miss, not a bare KeyError)." A union makes the contract explicit at the type level. **What would reverse it:** if callers overwhelmingly prefer exception-based flow control — but the typed miss is more defensible for a protocol.
- **Decision:** The hosted-docs adapter searches across all documents in an owner's library (via `list_membership`) rather than requiring a pre-scoped document set. **Why:** the real store's `AccountLibrary.load` returns all document_ids for an owner; scoping would add a parameter the real store doesn't have. **What would reverse it:** if performance degrades on large libraries — but the spec says "honest lexical is enough."

### Assumptions surfaced (rigor #1)
- The twin-notes adapter scopes to a single `asset_id` (one asset's twin substrate). If the research loop needs cross-asset search, a new adapter wrapping `list_twins` across multiple assets would be needed — this sprint doesn't build that.
- The hosted-docs adapter scopes to a single `owner_id`. Same cross-scope concern applies.
- The `_score` function uses a simple coverage ratio (`len(query) / len(text)`). This is intentionally naive — the conformance kit only asserts that the fixture doc ranks first, not that the ranking is optimal.

### Steelman of rejected alternative (rigor #2)
- **Richer contract (filters, pagination, embeddings):** Exa/Tavily expose faceted search, date ranges, embedding-based reranking. The two-verb bet is OpenAI's universal-connector evidence + swap-freedom. If the reference adapters need awkward contortions (e.g., the twin-notes adapter can't find relevant notes without embeddings), that is signal. Current evidence: substring matching works for the conformance fixtures. Real-world recall on production corpora is SPR-07/08's concern — they'll surface the falsifier if it exists.
- **Three verbs (search, fetch, traverse):** If the research loop measurably needs link-graph traversal (follow `supported_by` edges between twin notes) to match recall, the contract is wrong. That evidence gets recorded, not suppressed (W6 falsification hook). Current evidence: the twin-notes store has no graph edges — `source_spawn_id` and `investigation_id` are flat references, not traversable links.

### Open questions discovered
- **Cross-asset/cross-owner search:** the current adapters scope to one asset_id / owner_id. Does the research loop need cross-scope search? — answer: SPR-05 (the consumer) can answer this.
- **Performance on large corpora:** substring matching over all notes/documents is O(n). If an asset has thousands of twin notes, search may be slow. — answer: benchmark when real corpora arrive (SPR-07/08).
- **Graph traversal falsifier:** the twin-notes store has `source_spawn_id` and `investigation_id` but no `supported_by` edges. If future twin-note schemas add edges, the W6 falsifier becomes testable. — answer: monitor in SPR-05/07/08.

### Next sprint can start when
- This sprint's commits are merged to the campaign branch. SPR-05 (reads twin notes through the protocol) and SPR-07/08 (acquisition outputs become corpora) both depend on this contract being available.
