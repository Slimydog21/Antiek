## Sprint SPR-06 — Handoff

### Status
DONE (reworked twice — 8 review findings fixed across 2 rounds, all gates green)

### Rework round 1 (2026-07-11)
An independent adversarial reviewer rejected the initial deliverable with 5 confirmed findings. All 5 fixed:

1. **MAJOR — Clock injection.** Adapters and BrokenProvenanceAdapter now accept a `now_fn` parameter (defaults to `datetime.now(UTC)`). No `datetime.now` calls remain inside `substrate/corpus_contract/`. Two fetches of the same immutable record now return deterministically equal provenance. Provenance docstring updated.
2. **BLOCKER — Structural read-only.** Reader protocols narrowed to expose only the read methods adapters use (`list_twins` for twin notes; `get_document` + `list_membership` for hosted docs). Reader stored in name-mangled `__reader` attribute (not `_reader`). `assert_read_only` rewritten to verify no public attribute exposes a reader-protocol instance (duck-type check for reader methods), not just name-prefix checking. `runtime_checkable` removed from reader protocols (structural typing only).
3. **MAJOR — Hardened `assert_search_retrieval`.** Now additionally asserts: (a) non-matching decoy docs are NOT ranked above the seeded doc, (b) returned scores are non-increasing, (c) a query matching nothing returns zero hits.
4. **BLOCKER — Negative static type proof.** `tests/type_check_wrong_adapter.py` contains a wrong-signature adapter (`search(int)` instead of `str`, `fetch` returns `str` instead of `FetchResult`). Test runs mypy programmatically and asserts it reports `assignment` error — proof the Protocol rejects bad adapters.
5. **BLOCKER — Owner scope enforcement.** `hosted_docs.fetch` now checks `list_membership(owner_id)` before calling `get_document`. A `document_id` outside the owner's scope returns `CorpusMiss`. Cross-owner test added.

### Rework round 2 (2026-07-11)
Re-adjudication resolved findings 2/3/4 from round 1 but left findings 1/5/6. All 3 fixed:

1. **Finding 1 — Determinism proven, not just possible.** All adapter constructions in the test suite now pass a fixed `_fixed_now` clock (2026-01-01 UTC). Conformance kit gains `assert_fetch_determinism`: two fetches of the same id with the same fixed clock produce equal `CorpusDocument` (including `provenance.retrieved_at`). Kit module docstring updated to document clock discipline: wall-clock default is production ergonomics only; the kit never relies on it.
2. **Finding 5 — Cross-owner test proves the right thing.** Previous test fetched an id absent from the store entirely (unknown-id miss, not cross-owner denial). Fixed: store is seeded with a document that EXISTS and belongs to owner-B; adapter scoped to owner-A fetches that id; asserts `CorpusMiss`. The denial is purely owner-scope enforcement.
3. **Finding 6 — Ruff clean.** Removed unused `FetchResult` import from `tests/type_check_wrong_adapter.py:12`. Reran ruff over all owned files — clean.

Residual limits (honesty):
- Finding 2: Python has no visibility modifiers. A determined caller can access the name-mangled `_Adapter__reader` by spelling out the class name. The double-underscore prevents casual access but does not enforce encapsulation at the language level. The reader-protocol duck-type check inspects for common read-method names (`list_twins`, `get_document`, `list_membership`); a reader with an unusual API surface might slip through, but such a reader would not satisfy the adapter's type annotation either.

### Files touched
- `substrate/corpus_contract/__init__.py:1-31` — package init, public API exports (CorpusAdapter, CorpusHit, CorpusDocument, CorpusMiss, Provenance, FetchResult)
- `substrate/corpus_contract/protocol.py:1-112` — typing.Protocol (CorpusAdapter) with search/fetch; CorpusHit (id, score, snippet); CorpusDocument (content, provenance); CorpusMiss (typed, not bare KeyError); Provenance (source_kind, origin_ref, retrieved_at — clock-injected via adapter's now_fn)
- `substrate/corpus_contract/adapters/__init__.py:1-1` — subpackage marker
- `substrate/corpus_contract/adapters/twin_notes.py:1-137` — TwinNotesCorpusAdapter over TwinNoteReader protocol (narrowed: only list_twins); honest substring matching; clock injected via now_fn; reader stored in __reader (name-mangled)
- `substrate/corpus_contract/adapters/hosted_docs.py:1-140` — HostedDocsCorpusAdapter over HostedDocReader protocol (narrowed: only get_document + list_membership); honest substring matching; clock injected via now_fn; fetch enforces owner scope via list_membership check
- `substrate/corpus_contract/conformance.py:1-279` — reusable conformance kit: 8 assert helpers (assert_search_retrieval hardened with decoy exclusion + score ordering + zero-hits; assert_fetch_determinism for deterministic replay proof) + assert_read_only rewritten (structural, not name-prefix) + BrokenProvenanceAdapter red-proof (now accepts now_fn)
- `tests/test_corpus_contract.py:1-347` — 21 tests: 8 twin-notes (includes determinism), 9 hosted-docs (includes determinism + cross-owner), 3 broken-adapter red-proof, 1 negative type proof (mypy)
- `tests/type_check_wrong_adapter.py:1-32` — wrong-signature adapter for negative static type proof
- `substrate/corpus_contract/WIRING.md:1-64` — frozen-file wiring needs + doctrine invariants

### Milestones
- [x] M1: Protocol + document type — VERIFIED (mypy --strict green, protocol conformance type tests in protocol.py, negative type proof via mypy rejection of wrong-signature adapter)
- [x] M2: Reference adapter: twin notes — VERIFIED (passes conformance kit, zero writes interface-proven via TwinNoteReader protocol, reader stored in __reader)
- [x] M3: Reference adapter: hosted documents — VERIFIED (passes same conformance kit, fetch enforces owner scope)
- [x] M4: Conformance kit + tests + WIRING.md — VERIFIED (kit runs against both adapters, broken-adapter red-proof included, search retrieval hardened)

### Verification gate results (verbatim, 2026-07-11)
```
$ .venv-wt/bin/python -m pytest tests/test_corpus_contract.py -q
21 passed in 0.32s

$ .venv-wt/bin/mypy substrate/corpus_contract/ --strict --ignore-missing-imports
Success: no issues found in 6 source files

$ .venv-wt/bin/ruff check substrate/corpus_contract/ tests/test_corpus_contract.py tests/type_check_wrong_adapter.py
All checks passed!
```
- seam purity: pass (all changes within owned files: substrate/corpus_contract/* + tests/test_corpus_contract.py + tests/type_check_wrong_adapter.py)

### WIRING.md entries added (frozen-file needs documented, not edited)
- `substrate/engagement_spine/__init__.py` → re-export TwinNotesCorpusAdapter (SPR-05 consumes twin notes through the protocol)
- `substrate/marketplace_host/__init__.py` → re-export HostedDocsCorpusAdapter (SPR-07/08 acquisition outputs become corpora)
- `runtime/research_loop.py` (or equivalent) → accept CorpusAdapter protocol, not concrete store handles

### Decisions made mid-flight
- **Decision:** Accept a reader protocol (TwinNoteReader / HostedDocReader) rather than the full store (EngagementStore / HostStore). **Why:** the spec demands zero writes be interface-proven, not conventional. A reader protocol with no write method makes read-only structural. **What would reverse it:** if a future adapter needs write-through caching (unlikely — doctrine I-8 is binding).
- **Decision:** Search uses simple substring matching, not TF-IDF or embeddings. **Why:** the spec says "honest lexical matching" and "no embedding dependency." The conformance kit's retrieval assertion (fixture doc with exact query phrase must rank first) works with substring. **What would reverse it:** if recall measurably degrades on real corpora — but that's the store's concern, not the contract's.
- **Decision:** `FetchResult = CorpusDocument | CorpusMiss` (union type) rather than raising exceptions. **Why:** the spec says "fetch of an unknown id has one documented behavior (typed miss, not a bare KeyError)." A union makes the contract explicit at the type level. **What would reverse it:** if callers overwhelmingly prefer exception-based flow control — but the typed miss is more defensible for a protocol.
- **Decision:** The hosted-docs adapter searches across all documents in an owner's library (via `list_membership`) rather than requiring a pre-scoped document set. **Why:** the real store's `AccountLibrary.load` returns all document_ids for an owner; scoping would add a parameter the real store doesn't have. **What would reverse it:** if performance degrades on large libraries — but the spec says "honest lexical is enough."
- **Decision (rework):** Inject clock via `now_fn` parameter rather than a `Clock` protocol or dependency-injection framework. **Why:** a simple callable `() -> datetime` is the minimal injection surface. A Clock protocol would add a type for one method; a DI framework would violate §16 REJECT. **What would reverse it:** if multiple clock sources need distinguishing (unlikely — the contract only needs UTC timestamps).
- **Decision (rework):** Name-mangle reader with `__reader` (double underscore) rather than a closure-based private capture or a separate module-private store. **Why:** Python's name mangling makes `__reader` inaccessible as `adapter._reader` from outside the class — it becomes `adapter._TwinNotesCorpusAdapter__reader`. This is the strongest encapsulation Python provides without metaclass tricks. **What would reverse it:** if a subclass needs to access the reader (would require explicit `_Adapter__reader` spelling — acceptable for subclasses that know their parent).
- **Decision (rework):** Owner scope enforcement in `fetch` via `list_membership` check rather than scoping the reader or restricting at the store level. **Why:** the adapter is the enforcement point — the store doesn't know about the adapter's declared owner scope. Checking membership before `get_document` is the cheapest correct fix. **What would reverse it:** if `list_membership` becomes a performance bottleneck (unlikely for single-owner queries).
- **Decision (rework 2):** Prove determinism with a fixed `_fixed_now` clock in every test adapter construction, plus an explicit `assert_fetch_determinism` conformance helper. **Why:** the first rework round injected `now_fn` but the test suite never exercised it with a fixed value — determinism was architecturally possible but not proven. The conformance kit's module docstring now states the wall-clock default is production ergonomics only. **What would reverse it:** if a future adapter needs per-call clock variation for deduplication (unlikely — provenance timestamps are monotonic).

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
