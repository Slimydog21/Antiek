# SPR-01 Handoff — D2 Anchored Comments Schema and Event Contract

Status: **rework complete; final different-lineage re-review required**. Do not merge, push, enable production, or start SPR-02 from this document alone.

- Branch: `d2/spr01-feedback-schema-migration`
- Worktree: `/Users/slimydog/Antiek/worktrees/d2-spr01-feedback-schema`
- Baseline: `0bb7b76ff47e1b42bf66bc0f016e75e91578fa94`
- Implementation tip: `edf21f55ef9671359db21ef1914220443256a6a5`
- Canonical spec: `specs/antiek-voicenote-2026-08-28-anchored-comments/sprint-01-annotation-schema-store.html`
- Accepted D2 package aggregate: `d54b65157443df6aa8ffdecabf23149e19df4cc51b261cee6da486bfed4ddfe8`

## Delivered contract

### Migration SQL and recovery

`substrate/feedback/migrations.py::migrate_feedback_v41(primary_con)` remains the sole v40→v41 owner. It creates exactly the four active temp tables, four quarantine tables, and `feedback_provenance`, plus the spec index:

```sql
CREATE INDEX IF NOT EXISTS idx_feedback_provenance_owner
  ON feedback_provenance(owner_user_id,thread_id,ref_index);
```

The primary writer flock stays held across `started → temp_created → copied → renamed → completed`. Each phase commits independently with CAS markers and catalog/row digests. Resume verifies the committed phase before mutation. The runner refuses pre-existing target objects, including case variants and foreign-schema names, before v41 creation.

Every legacy source row is represented exactly once by either an active temp row or its quarantine `original_row_sha256`. Cascade decisions use full source IDs, never the bounded `original_*` audit columns. An active thread requires:

- at least one item with a contiguous sequence beginning at 1;
- every source item to be active;
- exactly one active work row;
- every source attempt for that work row to be active.

Missing roots/work, malformed dependents, and overbound-ID prefix collisions quarantine the owning aggregate. Evidence JSON contains per-field byte length, SHA-256, and truncation state; values over 256 bytes are never copied raw.

### Event and codegen diff

The write schema is exactly v41. The typed union includes the full D2 payload set, including:

- `investigation.start_requested` and `investigation.spawned_from` with conditional `launch_kind="d2_branch"`, the complete owner/dispatch/parent-artifact/feedback/child/start tuple, bounded context hash, and partial-tuple rejection while legacy chase shapes remain readable;
- `agent.work.d2_transitioned` with `event_schema_version=41`, closed `D2QueueTransitionReason`, owner/dispatch/work/attempt/provider/cost tuple, bounded IDs, hashes, and timestamp;
- highlight, dispatch, deliverable edit, owner-role, and full-tuple resolution payloads;
- a read-only v40 resolution adapter that never re-emits or claims `edit_applied`;
- exact v41 envelope locking for all unconditional D2 actions and conditional D2 branch launches.

`tools/codegen/emit_types.py` is the source of `apps/reading/src/generated/types.ts`. The committed TypeScript fixture constructs and narrows the D2 transition and both D2 branch variants under `tsc --strict`.

### Provenance result shape

`feedback_provenance` has the frozen owner/thread/ref index key, eight-ref bound, node/edge/chunk/claim/document/IP-holder pointers, closed status/holder/reason vocabularies, lower-case source digest, and the owner index above. This branch owns the schema/result contract only; no parallel provenance writer or annotation store was added.

## Exact changed paths

- `apps/reading/src/generated/types.ts`
- `substrate/feedback/SPR01_HANDOFF.md`
- `substrate/feedback/migrations.py`
- `substrate/feedback/service.py`
- `substrate/schemas/__init__.py`
- `substrate/schemas/events.py`
- `substrate/write/event_outbox.py`
- `tests/_migration_concurrent_writer.py`
- `tests/_migration_crash_runner.py`
- `tests/fixtures/v41_ts_roundtrip.ts`
- `tests/substrate/dispatch/test_nd_attribution.py`
- `tests/test_event_schema_roundtrip.py`
- `tests/test_feedback_event_rollback.py`
- `tests/test_feedback_event_schema_v41.py`
- `tests/test_feedback_migration_concurrency.py`
- `tests/test_feedback_migration_digest_vectors.py`
- `tests/test_feedback_migration_kill_resume.py`
- `tests/test_feedback_migration_v41.py`
- `tools/codegen/emit_types.py`

## Fresh gate evidence at `edf21f55ef9671359db21ef1914220443256a6a5`

```text
/Users/slimydog/Antiek/.venv/bin/python -m pytest   tests/test_feedback_migration_v41.py   tests/test_feedback_migration_kill_resume.py   tests/test_feedback_migration_concurrency.py   tests/test_feedback_migration_digest_vectors.py   tests/test_feedback_event_schema_v41.py   tests/test_event_schema_roundtrip.py   tests/test_feedback_event_rollback.py   tests/test_feedback_routes.py   tests/test_feedback_store.py -q
→ 114 passed, 1 warning in 31.70s; exit 0

/Users/slimydog/Antiek/.venv/bin/python -m pytest tests/substrate/dispatch/test_nd_attribution.py -q
→ 12 passed in 0.49s; exit 0

/Users/slimydog/Antiek/.venv/bin/python -m pytest   tests/test_start_research_owner_api.py   tests/test_loop_one_orchestrator.py   tests/test_orchestrator_chase.py   tests/test_sprint11_api.py   tests/test_weekly_report.py -q
→ 64 passed, 3 warnings in 24.59s; exit 0

/Users/slimydog/Antiek/.venv/bin/ruff check <all changed Python files>
→ All checks passed!; exit 0

/Users/slimydog/Antiek/.venv/bin/python tools/codegen/check_staleness.py
→ OK [events]; OK [contracts]; exit 0

git diff --check
→ silent; exit 0
```

Real-store coverage includes DuckDB 1.5.4 migration execution, idempotent rerun, kill/resume after every committed phase, concurrent complete-aggregate writers, add/update/delete drift refusal, catalog/table/index tamper refusal, malformed Unicode/SQL-like values, missing root/work quarantine, full-ID prefix collision isolation, rollback, and outbox replay identity. The valid seed produces zero quarantine rows. Deliberately malformed fixtures produce only their source/cascade rows; there is no synthetic runner row.

No browser gate applies to this backend/schema slice. The real generated frontend artifact is compiled through `tests/fixtures/v41_ts_roundtrip.ts` with `tsc --noEmit --strict` inside the 114-test lane.

## Review record

- Event repair review: `/Users/slimydog/Antiek/.infinite/prime-goal-2026-08-28/review-spr01-events-fix-glm.md` → `ACCEPT`.
- Migration F1-F3 review: `/Users/slimydog/Antiek/.infinite/prime-goal-2026-08-28/review-spr01-migration-f1-f3-fix-glm.md` → `ACCEPT`.
- Migration F4-F8 review: `/Users/slimydog/Antiek/.infinite/prime-goal-2026-08-28/review-spr01-migration-f4-f8-fix-glm.md` → `ACCEPT`.
- D1 catalog review: `/Users/slimydog/Antiek/.infinite/prime-goal-2026-08-28/review-spr01-migration-d1-fix-glm.md` → `ACCEPT`.
- Final security/owner-isolation review at `ae4bc0292`: `/Users/slimydog/Antiek/.infinite/prime-goal-2026-08-28/review-spr01-final-security-glm.md` → `ACCEPT`, zero CRITICAL/HIGH/MEDIUM findings.
- Final whole-range review at `ae4bc0292`: `/Users/slimydog/Antiek/.infinite/prime-goal-2026-08-28/review-spr01-final-full-range-codex.md` → `REQUEST CHANGES` for two P1 findings and two P2 findings.
- P1 repairs landed in `cb2b919bcfe4d4c653864a795944b86926a80cca`: complete D2 event variants and full-source, no-partial aggregate cascade. P2 repairs pin the ND schema test to exactly 41 and replace this handoff.
- Final repair review at `6d0b0b13c`: `/Users/slimydog/Antiek/.infinite/prime-goal-2026-08-28/review-spr01-final-repair-codex.md` → `REQUEST CHANGES` for legacy spawned events accepting D2-only owner fields.
- Class-aware legacy owner-lineage repair landed in `edf21f55ef9671359db21ef1914220443256a6a5` with a red/green regression. **A fresh final whole-range and security delta review is still required.**

## Remaining limitations and blockers

1. Final different-lineage acceptance of `0bb7b76ff..edf21f55ef9671359db21ef1914220443256a6a5` is pending. This is the only SPR-01 acceptance blocker claimed here.
2. A narrow historical v39 resolution-event window fails closed on replay; the authorized frozen adapter covers v40. This is recorded LOW, not silently upgraded.
3. Migration copies/digests use whole-table `fetchall()` under the exclusive migration flock; memory scales with legacy feedback-table size.
4. `D2_FEEDBACK_V41_CRASH_AFTER` is a test-only, env-gated hard-exit hook in production code and must remain unset outside the crash harness.
5. Repository-wide `pytest -q` is not a bounded deterministic gate: an untouched NotDiamond timeout test can flake under load and unrelated tmp-tree teardown can stall. The exact SPR-01, owner-launch regression, and deterministic prefix gates above are green.

## Next action

Request a bounded different-lineage delta/full-range re-review of `edf21f55ef9671359db21ef1914220443256a6a5` against the two final P1 reproductions, the complete D2 event contract, this handoff, and all prior artifacts. Close the claim only if both final correctness and security reviewers return `ACCEPT`. SPR-02 remains blocked until then.
