# Knowledge-unit deposit contract — extension of insight/question nodes (AFF SPR-04)

**Decision date:** 2026-05-31
**Status:** ✅ Committed
**Owner:** Antiek Flywheel Foundation SPR-04
**Base SHA:** `d7ba618` (origin/main tip in the SPR-04 worktree; has SPR-01 anti-stranding gate, SPR-02 invariant registry, SPR-03 boundary-lint). The spec header's `e779537`/`ebfb36a` are stale — `EVENT_SCHEMA_VERSION` is `24` at this tip.

This is the flywheel's **deposit half**: the shape every investigation deposits and every downstream sprint (SPR-06 retrieval, SPR-07 dedup, SPR-08 groundedness, SPR-09 benchmark) trusts. The win condition was narrow and mechanical: **extend the existing atom, do not fork a parallel one**. The diligence pass below confirms the atom already ships — so this sprint is overwhelmingly extend/compose, and the genuinely net-new surface is three fields plus a conformance test.

---

## Why this extends `nodes.py` rather than forking a new module

DRW SPR-01 owns `node_type='insight'|'question'` and their only sanctioned writers (`promote_insight`/`promote_question` in `substrate/graph/insight_question.py`). Forking a parallel "knowledge_unit" node type would create a **second atom** and break the "one entity everywhere" property — the moat — where an insight created in Research is *the same node* when Read surfaces it, Write drags it into an outline, and Speak deepens it. So `KnowledgeUnitContract` is added to `substrate/contracts/nodes.py` (the existing node-contract module), composing the reused identity/scope/confidence fields and adding only what the flywheel needs. No new graph store, table, or migration; no second writer.

---

## Reused-vs-added table (rigor #1)

VERIFIED against the live tip by reading each surface in full.

| Contract field | Status | Source (file:line) |
|---|---|---|
| `node_id` | **reused** | content-addressed `content_addressed_id(node_type, canonical_text)`; `substrate/graph/insight_question.py:112-119`, `:240`, `:322`; contract shape `substrate/contracts/nodes.py:62` |
| `node_type` (`insight`\|`question`) | **reused** | graph CHECK `substrate/graph/schema.py:111-115`; contracts `nodes.py:63/83` |
| `text` | **reused** | the node's `canonical_label`; `insight_question.py:272-282` (`insert_node(canonical_label=text, ...)`); contract `nodes.py:64` |
| `investigation_id` | **reused** | rides the `GRAPH_NODE_INSERTED` event envelope + the `supported_by` edge (`edges.investigation_id`, `schema.py:146`) — **NOT a `nodes` column** (verified: `nodes` has no `investigation_id`, `schema.py` nodes DDL). `insight_question.py:_add_provenance_edges` L133 passes it onto the edge. Contract `nodes.py:65/85` |
| `confidence` | **reused** | the four-value `ConfidenceLevel`; stamped into node metadata at `insight_question.py:253` (`"confidence": confidence`); contract vocab `nodes.py:40` |
| claim→chunk→doc provenance (`source_document_id` + `chunk_id`) | **reused** | the `supported_by` edge's own columns, written by `_add_provenance_edges` (`insight_question.py:133`, `:283-293`) → `GraphEdgeInsertedPayload.source_document_id`/`chunk_id` (`events.py:1244-1245`); mirrored into node metadata at `insight_question.py:267-270` for the marginalia no-claim-target path. Surfaced as the new `ProvenanceLink` object. |
| `graph_scope` (`depth`) | **reused** | `_PROMOTION_GRAPH_SCOPE = "depth"` (`insight_question.py:77`); contract `nodes.py:66/86` |
| `has_embedding` | reused (on sibling contracts; **not carried** on KnowledgeUnitContract — embedding is derived data, irrelevant to deposit reuse) | `nodes.py:68/87` |
| **`retrieval_key`** | **ADDED** | net-new surfaced field; equals `node_id` by construction (validated). The content-addressed key already exists; what is new is *exposing it under a named contract field* so SPR-06 retrieval has a handle that does not depend on the row column name. |
| **`servability`** (`ServabilityTag`) | **ADDED, linked to existing classifier** | typed against `ContentClass` + `FULL_TEXT_SERVABLE` from `substrate/contracts/servable.py:39-48`; the *answer* is read from `substrate.books.servability.servability_of` + `is_servable_full_text` (`substrate/books/servability.py:90-126`) — deny-by-default is **not re-derived**. |
| **`groundedness_score`** | **ADDED** | `Optional[float] = None`, nullable, `None` until SPR-08. No existing node/contract carries it (see below). |

### No existing `groundedness_score` on any node/contract — VERIFIED

The grep for `groundedness_score` finds it **only** on `GroundednessScoredPayload.groundedness_score` (`substrate/schemas/events.py:1465`) — a *per-synthesis* claim-entailment event from Foundation v2 SPR-02 that scores a whole synthesis, **not a single deposited node**. No node row, no node-contract, and no graph table carries a per-unit groundedness score. So adding the slot to `KnowledgeUnitContract` is genuinely net-new at the node/unit level (and intentionally distinct from the synthesis-level event — documented in the contract docstring).

### Honest shrink

The §9.0 answer is **not** attached at deposit today — `promote_insight`/`promote_question` write the node + provenance edge but never call the servability classifier, and the node row has no servability column. So the servability tag is honestly net-new *at the unit level*: it is assembled by `knowledge_unit_of` reading the classifier's answer for the source's `content_class`. The sprint did not shrink further than the diligence already predicted: retrieval-key surfacing, servability tag, and the nullable groundedness slot are the three added things; everything else is reuse.

---

## What was built

1. **`substrate/contracts/nodes.py`** — `KnowledgeUnitContract` (frozen, `extra="forbid"`, matching the sibling node contracts) plus two nested frozen models:
   - `ProvenanceLink` — `source_document_id` + `chunk_id`, **both required** (a unit with no chunk has nothing for SPR-06 to point at and nothing for §9.0 to gate). This is the field the non-vacuity test drops.
   - `ServabilityTag` — `content_class: Optional[ContentClass]` (typed against `servable.py`'s Literal, **not** free-form; `None`/unknown ⇒ non-servable) + `serves_full_text: bool`, with a `model_validator` enforcing deny-by-default (a class outside `FULL_TEXT_SERVABLE` may never claim `serves_full_text=True`).
   - `retrieval_key` validated `== node_id`.
   - `groundedness_score: Optional[float] = None`.
2. **`substrate/graph/insight_question.py`** — `servability_tag_for(content_class, taken_down=...)` (reads the §9.0 classifier's answer) and `knowledge_unit_of(con, node_id, content_class=...)` which **reads** a deposited node + its `supported_by` edge from the same write-locked connection and projects it onto a validated `KnowledgeUnitContract`. The deposit path (`promote_insight`/`promote_question` → `_with_connection` → `connect_write`) is **unchanged**; the helper writes nothing.
3. **`tests/test_contracts_conformance.py`** — a real deposit driven through `promote_insight` (grounded on a seeded document/chunk/claim) projected to the contract, with the non-vacuity drops.

---

## `gap_resolution` variant — DEFERRED (expressible via the existing path)

The spec permits a `gap_resolution` unit variant *only if* expressible via the existing question→`resolved_by` edge path. It is — a resolved gap is a `question` node carrying a `resolved_by` edge to the answering insight (`promote_question(resolved_by=[...])`, `insight_question.py:301-361`). Because it is already expressible with no new node type and no new contract field (it is just a `question`-typed `KnowledgeUnitContract` whose resolution lives on an edge), **no separate variant is added**. SPR-07 gap-detection reads `resolved_by` directly. Recorded as deferred rather than inventing a node type.

---

## Steelman of the rejected alternative (rigor #2)

**"A synthesis doc is enough — skip structured units."** The synthesizer already produces a written synthesis per investigation; one good prose synthesis is more readable than a pile of atoms and is what the operator actually consumes. Why structure deposits at all — just retrieve over prose later?

**Answer — a blob is depositable but not *compoundable*:**
- **No stable retrieval key.** You cannot assign a stable, content-addressed key to a paragraph; the content-addressed `node_id` is what lets SPR-06 find *the same insight* across investigations.
- **No dedup.** SPR-07 deduplicates two phrasings of the same insight via the content-addressed `node_id`; prose has no identity to collapse on.
- **No per-chunk trust-gate.** §9.0 servability is per-source, per-chunk (`servable.py` deny-by-default keys off a document's `content_class`); a prose blob mixing servable and gated sources cannot be trust-gated per claim. The `ProvenanceLink` anchors each unit to exactly one chunk→doc so the gate has something to decide on.

The synthesis doc remains valuable for *reading*; it is just not the *compounding unit*. Both coexist.

---

## Schema-bump decision (rigor #5) — NO BUMP

**Payload changed? NO. `EVENT_SCHEMA_VERSION` left at 24; `types.ts` unmodified.**

The `GRAPH_NODE_INSERTED` deposit event (`GraphNodeInsertedPayload`, `events.py:1218-1230`) carries `node_id`, `canonical_label`, `node_type`, `graph_scope`, `has_embedding` — and the provenance (`source_document_id`/`chunk_id`/`investigation_id`) rides the **edge** event (`GraphEdgeInsertedPayload`, `events.py:1233-1248`), not the node event. `KnowledgeUnitContract` is satisfiable **entirely from existing node + edge + metadata fields** plus the classifier's answer (computed at assembly time, not persisted as a new event field). No event payload gained a field, so no bump.

Verified: `python tools/codegen/check_staleness.py` exits **0** (both events and contracts in sync) with `events.py` untouched.

### Contracts-TS codegen — `KnowledgeUnitContract` intentionally NOT emitted to TS

`tools/codegen/emit_contracts.py` uses an **explicit allowlist** (`CONTRACT_MODELS`) — it does not auto-discover classes in `nodes.py`. `KnowledgeUnitContract`/`ProvenanceLink`/`ServabilityTag` are **deliberately omitted** from `CONTRACT_MODELS` and `substrate.contracts.CODEGEN_CONTRACTS`: the first TS consumer is SPR-06 (retrieval), which does not exist yet. Emitting now would bump `CONTRACT_SCHEMA_VERSION` and regenerate `contracts.ts` for a consumer that doesn't exist. They are exported from `substrate/contracts/__init__.py` for **Python** consumers (the test, SPR-06/07/08). When SPR-06 lands its TS surface, add them to the allowlist and bump `CONTRACT_SCHEMA_VERSION` then. This keeps both codegen gates green untouched this sprint.

---

## What SPR-06/07/08 can build on

- **SPR-06 (retrieval)** can start: the retrieval key (`retrieval_key == node_id`) is a stable, surfaced contract field, and a deposited unit conforms. When it adds a TS consumer, put the three new models on the `CONTRACT_MODELS` allowlist and bump `CONTRACT_SCHEMA_VERSION`.
- **SPR-07 (dedup)** can start: exact-text dedup already rides the content-addressed `node_id`; near-dup is SPR-07's to add.
- **SPR-08 (groundedness)** can start: the nullable `groundedness_score` slot exists and conformance tolerates `None`, so SPR-08 lands a value without re-cutting this contract (a `model_copy(update={"groundedness_score": ...})` validates — proven in the test).

---

## Reconsider-if

- If SPR-06 needs the §9.0 answer *persisted on the node row* (not recomputed at assembly), that is a new node column + a real schema migration + likely an event-payload field — at which point the no-bump decision flips. Today the answer is cheap to recompute from `content_class`, so we do not persist it.
- If a future deposit path needs grounding that is not a single chunk (multi-chunk units), `ProvenanceLink` becomes a tuple and the conformance shape changes — out of scope here.

---

## Sharpen pass (2026-05-31) — two SEND-BACK blockers + the fixture gap that hid them

The first cut passed only a happy-path fixture (real claim node + `supported_by` edge + `public_domain` source), which masked two defects. Both fixed; the fixture now drives the previously-uncovered paths.

### BLOCKER 1 — servable-allowlist DRIFT (crash on CC-BY)

`servability_tag_for("source_declared_open")` raised a `ValidationError`. Root cause was the exact second-owner drift the §9.0/boundary work exists to prevent: the §9.0 classifier (`substrate/books/servability.py` `_SERVABLE_STATUSES`) treats **four** statuses as full-text-servable — `public_domain, platform_authored, publisher_opted_in, source_declared_open` — but the contract's `FULL_TEXT_SERVABLE` (`substrate/contracts/servable.py`) listed only **three** (missing `source_declared_open`). For a CC-BY source the classifier said `serves=True`, the contract forced `content_class=None` (not in its allowlist), and `ServabilityTag(content_class=None, serves_full_text=True)` tripped the deny-by-default validator.

**Fix (single-owner):** `FULL_TEXT_SERVABLE` is now **DERIVED** from `substrate.books.servability._SERVABLE_STATUSES` (`frozenset(s.value for s in _CLASSIFIER_SERVABLE_STATUSES)`), and `source_declared_open` was added to the `ContentClass` Literal. Two **import-time drift-guard assertions** weld them: (1) every classifier-servable status must be representable in the `ContentClass` Literal; (2) `FULL_TEXT_SERVABLE` must equal the classifier's set exactly. A future hand-edit that re-forks the allowlist now fails at *import* (every test reds), not silently at runtime on a CC-BY source. The classifier remains the **single owner** of which statuses serve; the contract mirrors it. (`books/servability.py`'s *logic* is untouched — also touched by the staged §9.0 PR #38 on a separate branch — we only read its servable set as the source of truth.)

`FULL_TEXT_SERVABLE` is the `ServabilityStatus`-**value** vocabulary (status names), not the `content_class` column vocabulary; the classifier's `_SERVABLE_STATUSES` is the same vocabulary, so the derivation is type-aligned.

### BLOCKER 2 — empty `investigation_id` on question / marginalia units

`knowledge_unit_of` recovered `investigation_id` only from the `supported_by` edge. A **question** node grounds via `asks_about`/`resolved_by` (never `supported_by`), and a **user-authored marginalia** insight has `supported_by=[]` — both fell to `meta.get("investigation_id")`, but `promote_insight`/`promote_question` never wrote `investigation_id` into node metadata. Result: `investigation_id=''` on a unit deposited under a real investigation, which the contract accepted silently — SPR-07 dedup keyed on investigation scope would mis-bucket every question/marginalia unit.

**Fix (both halves landed):**
- **(a) Real id at deposit.** `promote_insight` and `promote_question` now stamp `investigation_id` into node `metadata` (the JSON `metadata` column, which rides the existing node insert — **no event-payload change, EVENT_SCHEMA_VERSION stays 24**). `promote_question` also now mirrors `chunk_id` into metadata (it previously mirrored only `source_document_id`), so a grounded question is recoverable by `knowledge_unit_of` (which has no `supported_by` edge to read for a question). The projection prefers the `supported_by` edge's `investigation_id` and falls back to the metadata mirror — single-sourced, the two always agree.
- **(b) Fail loud on the gap.** `KnowledgeUnitContract.investigation_id` now has `min_length=1`, and `knowledge_unit_of` raises a clear `ValueError` (not a `''` coercion) when no `investigation_id` is recoverable. A future projection gap reds at the contract boundary instead of conforming silently.

### Fixture (SHOULD-FIX)

Added to `tests/test_contracts_conformance.py` — each asserts `investigation_id` AND servability are **correct**, not merely non-crashing:
- (a) `source_declared_open` source → servable tag, no crash (direct `servability_tag_for` + full deposit→projection).
- (b) marginalia insight (`supported_by=[]`, metadata-only grounding) → `investigation_id == "inv1"`, not `''`.
- (c) `question`-node projection → `investigation_id` + servability correct, recovered from the metadata mirror.
- Plus: empty-`investigation_id` rejected by the contract; projection raises when the id is genuinely absent (a deliberately-blanked node); and a drift-guard test proving the two allowlists are welded and would red on divergence.

### Bump decision — STILL 24 (no event bump)

`investigation_id` is stamped into the node `metadata` JSON, which is already part of the `nodes` INSERT and is NOT a `GraphNodeInsertedPayload` field — so no event payload gained a field. `python tools/codegen/check_staleness.py` confirms `events` / `types.ts` **untouched**.

**Contracts-TS DID regenerate (one line).** Adding `source_declared_open` to the `ContentClass` Literal changed `ServableEntryContract.content_class` in `apps/reading/src/generated/contracts.ts` (that contract IS on the `CONTRACT_MODELS` allowlist and consumed by Read today — distinct from the still-unemitted `KnowledgeUnitContract`). Regenerated via `emit_contracts.py`; `check_staleness.py` exits **0**. The new knowledge-unit models remain off the allowlist as before (SPR-06 has no TS consumer yet).
