## Sprint SPR-02 — Handoff

### Status
done

### Files touched
- `substrate/schemas/events.py:495` — new ActionType `RESEARCH_PROVIDER_MEASURED = "research.provider.measured"` (additive, dotted-lowercase convention).
- `substrate/schemas/events.py:741` — `EVENT_SCHEMA_VERSION` 27→28 (additive: +1 ActionType member, no field removed/retyped, no new TypedPayload variant; bump-log comment at :725-740).
- `research/measurement/__init__.py` (new) — re-exports `MeasurementRecord`, `Outcome`, `TaskClass`, `classify`, `from_research_result`, `append_measurement`, `read_measurements`, `reconstruct_trajectory`, `MeasurementLogError`, `MEASUREMENT_RECORD_SCHEMA_VERSION`.
- `research/measurement/schema.py` (new) — `MeasurementRecord` frozen dataclass (12 fields, all required, every field doc'd with units/range/nullability/emit-vs-backfill); `Outcome` enum (success/partial/failed/timeout/budget_exceeded); `from_research_result()` proving INV-4 (reads only normalized ResearchResult fields + `raw_ref.handle`, rejects non-ResearchResult); `MEASUREMENT_RECORD_SCHEMA_VERSION=1` (decoupled from EVENT_SCHEMA_VERSION).
- `research/measurement/task_class.py` (new) — `TaskClass` enum (structured_extract/broad_gather/needle_in_haystack/multi_hop/unclassified), DRAFT, each with definition+example; `classify()` deterministic keyword heuristic with written priority rule (multi_hop>needle>structured>broad>unclassified, first-match-wins, unclassified escape hatch).
- `research/measurement/log.py` (new) — `append_measurement()` validate-then-atomic-append writer (writes NOTHING on reject; `_validate_record` raises `MeasurementLogError` naming the field; `_append_jsonl` byte-identical to `substrate/event_log/events.py:172-180`); `read_measurements()` forward/backward-compat reader (tolerates missing fields, unknown fields, unknown enum values, malformed lines).
- `research/measurement/reconstruct.py` (new) — `reconstruct_trajectory()` returns ordered `MeasurementRecord` list (sorted by emitted_at + correlation_id tiebreak) scoped to one investigation's `.measurements.jsonl` (no bleed).
- `tests/research/test_measurement_log.py` (new) — 48 tests: schema surface, from_research_result INV-4, writer happy-path+atomicity, 4 mandatory negative reject tests (each proven raise+write-nothing), mixed-version reader roundtrip, reconstruction ordering+scoping, task-class determinism.
- `apps/reading/src/generated/types.ts` — regenerated via `tools/codegen/emit_types.py`; new ActionType const key `RESEARCH_PROVIDER_MEASURED` emitted (:146). Events codegen staleness check OK; contracts.ts staleness is pre-existing and out of scope.
- `.gitignore:85` — `!/research/measurement/` un-ignore exception (matches SPR-01's `!/research/providers/` pattern).

### Milestones
- [x] M1: Read existing schema + version anchor — `EVENT_SCHEMA_VERSION = 27` at `substrate/schemas/events.py:711` (now 28); ActionType enum at :57; Event envelope shape documented; existing reader tolerates unknown fields (forward-compat confirmed).
- [x] M2: Measurement record (schema v28) — `MeasurementRecord` 12-field frozen dataclass; `correlation_id = ResearchResult.raw_ref.handle` (the SPR-01-designated opaque join key); bump purely additive (+1 ActionType, +0 TypedPayload variants).
- [x] M3: Task-class taxonomy — 5-class enum, DRAFT, mutually distinguishable by written rule; `classify()` deterministic coarse prior (real classification is SPR-07's job); `unclassified` escape hatch so nothing is silently force-fit.
- [x] M4: Validated writer + compatible reader — writer validates before append, rejects (out-of-range confidence, missing field, negative cost, unknown task_class, NaN/inf, bool-as-int, empty strings) with field-named errors, writes nothing; reader tolerates older + unknown fields + unknown enum values + malformed lines; mixed-version roundtrip proven.
- [x] M5: Reconstruction query — `reconstruct_trajectory()` ordered + investigation-scoped (no bleed); end-to-end ResearchResult→record→append→reconstruct preserves normalized fields (INV-2).

### Verification gate results
- writerRejectsInvalid: **pass** (4 mandatory negative cases each raise + write nothing; mutation-tested by the lens).
- readerForwardCompat: **pass** (unknown fields + unknown enum values preserved, not crashed).
- readerBackwardCompat: **pass** (older-schema missing fields tolerated, no invented defaults).
- reconstruction: **pass** (ordered, no-bleed, correlation_id links to SPR-01 ResearchResult).
- atomicAppend: **pass** (`_append_jsonl` byte-identical to event_log reference; reject doesn't corrupt prior records).
- noRegressions: **95 passed** (48 measurement + 19 SPR-01 + 28 regression).
- Adversarial verify (workflow `wf_b9c3bfa1-8ec`, 4 lenses, round 1): **schema-leak-compat** CLEAN (live wire check: no provider-specific fields on the wire); **writer-rejects** CLEAN (mutation testing: disabling each guard fails its test, write-then-validate fails 7, stripping field names fails match); **reconstruction** CLEAN (INV-2 satisfied); **determinism-atomicity** CLEAN (byte-identical append, validate-before-append, observed-not-estimated).

### Decisions made mid-flight
- Frozen dataclass (not TypedDict/Pydantic) for `MeasurementRecord` — matches SPR-01 `ResearchResult` idiom; keeps the measurement layer dependency-light; immutability prevents in-place divergence from the log; lets the writer do its OWN field-named validation (Pydantic ValidationError buries the field name).
- `correlation_id = ResearchResult.raw_ref.handle` — the SPR-01-designated opaque join key to the raw payload; opaque by construction so no INV-4 leak.
- Measurement record is its OWN JSONL (`{investigation_id}.measurements.jsonl`), NOT a TypedPayload variant of the Event envelope. The field set isn't the Event envelope shape; embedding would force a new payload model + discriminated-union member + codegen interface for a flat 12-field record, and would inherit the Event envelope's `_safe` error-swallowing (wrong semantics — a rejected record is a caller bug that MUST raise). Most additive possible change: +1 enum member, +0 payload models.
- `MEASUREMENT_RECORD_SCHEMA_VERSION=1` decoupled from `EVENT_SCHEMA_VERSION=28` — action-vocabulary version and record wire-shape version evolve independently.
- Reader preserves append order (authoritative); `reconstruct_trajectory` sorts (emitted_at + correlation_id tiebreak) — mirrors event_log's split of raw trajectory read from validate_trajectory analysis.

### Assumptions surfaced (rigor #1)
- `test_committed_ts_matches_current_schema` (contracts.ts staleness) is pre-existing, confirmed failing on the parent branch before any SPR-02 change; caused by `substrate/contracts/` drift unrelated to events. Only the events codegen target was regenerated (now in sync).
- `test_distill_routes.py::test_challenge_with_no_provider_is_honest_503` is a pre-existing environment-dependent failure (dev env has a model configured → 200 not 503); not in the spec-defined regression set; not an SPR-02 regression.
- `classify()` is a COARSE PRIOR, not the router's real classification (SPR-07). Keyword heuristic deliberately short.
- `cost_usd`/`latency_ms` are OBSERVED (post-call, from `ResearchResult.cost/latency`), distinct from SPR-01 `CostModel` estimates — proven by `test_from_research_result_observed_not_estimated`.

### Steelman of rejected alternative (rigor #2)
- Embed the measurement record as a new `TypedPayload` variant in the Event envelope discriminated union, written via `emit_typed`. Steelman: reuses the Event envelope's `parent_event_id` span linkage, `policy_id` stamping, and automatic `trajectory()`/`seal_investigation()` inclusion with zero new storage code. Why it lost: (1) the measurement field set is NOT the Event envelope shape — forcing it under `Event.payload` makes it a nested payload, not a first-class trajectory row; (2) requires a new Pydantic payload model + union member + codegen interface for a flat 12-field record; (3) the Event envelope's `_safe` swallows write errors to stderr (telemetry must never break a synthesis) — but a REJECTED record is a caller bug that MUST raise; reusing `emit_typed` inherits the wrong error semantics; (4) the chosen approach is the most additive possible (+1 enum, +0 payload models). Where the alternative would have won: IF the measurement needed `parent_event_id` span linkage to a `role.call.start`, embedding would be correct — but the spec scopes it as standalone per-call telemetry with its own `correlation_id`.

### Open questions discovered
- TaskClass taxonomy is DRAFT pending operator ratification (master-spec open question). Real (semantic, calibrated) classification is SPR-07's job.
- Should the measurement record's `schema_version` track `EVENT_SCHEMA_VERSION` (v28) or stay decoupled (=1)? Chose decoupling (action-vocab version vs record wire-shape version evolve independently). One-line change if the operator prefers a single namespace.
- The measurement JSONL is NOT sealed to Parquet by the existing `seal_investigation()` (which only seals `{investigation_id}.jsonl`). A sealing path for measurement records is out of scope this sprint but will be needed before long-term storage — should reuse the JSONL→Parquet idiom. Noted for a future sprint.
- `outcome` for a budget_exceeded call that never ran: specified `cost_usd=spend-that-triggered-gate` (may be 0), `latency_ms=0`. SPR-07 will confirm pre-call budget_exceeded (call never made, cost=0) vs mid-call abort (partial spend). Schema supports both; semantics are the caller's at emit-time.

### Next sprint can start when
- SPR-07 (the learned router) can begin: the measurement schema + writer + reader + reconstruction are exported and importable from `research.measurement` — DONE. The router reads this log to learn provider/tier selection per task class.
- SPR-03/04 (Exa/Parallel adapters) can begin once the operator un-defers live provider calls; adapters will call `append_measurement` after each `answer()` to emit the trajectory event.

### Out-of-scope temptations encountered
- Wanted to wire `StubResearchProvider` to auto-emit a measurement on `answer()`; resisted (adapters emit in SPR-03/04; this sprint owns schema+writer+reader).
- Wanted to add a measurement-JSONL→Parquet sealing path; resisted (future sprint; noted in open questions).
- Wanted to implement the router's real (embedding/LLM-judged) task classification; resisted (SPR-07; `classify()` is a coarse prior).
- Wanted to add retry/budget/resilience around `append_measurement`; resisted (SPR-05/06).
- Wanted to fix the pre-existing contracts.ts codegen staleness while regenerating events; resisted (pre-existing drift in `substrate/contracts/`, another sprint's surface).
- Wanted to modify SPR-01's `types.py`/`base.py` to add a measurement-emission hook; resisted (read-only dependencies; `from_research_result` reads without modifying).
