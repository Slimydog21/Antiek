# SPR-01 Handoff — D2 Anchored Comments (Feedback Schema Migration + v41 Event Schema)

Status: **feature-complete, blocked on independent review** (subagent infrastructure failure — 14 consecutive probe deaths across 4 lineages; see Review status).

- Branch: `d2/spr01-feedback-schema-migration` (worktree, NOT pushed — sprint forbids push)
- Baseline: `origin/main` @ `0bb7b76ff47e1b42bf66bc0f016e75e91578fa94`
- Commits (oldest → newest):
  - `2817545a` feat(feedback): add v41 migration runner
  - `9b739a4f3` fix(feedback): repair review P0/P1 findings in v41 migration
  - `96d1ed82` test(feedback): add real-process kill/resume gate for v41 migration
  - `5a0bf05be` test(feedback): add concurrent-writer exclusion gate
  - `bebb6fc23` fix(feedback): refuse rename when baseline drifts after copy
  - `3203b889c` style(feedback): ruff fixes for drift pre-check
  - `8109a9653` test(feedback): pin v41 digests to spec-derived golden vectors
  - `880442f1e` test(feedback): pin DuckDB catalog DDL normalization; drop dead helper
  - `2ca71eaae` feat(events): add D2 v41 typed payloads and shared enums
  - `ce30c9857` feat(events): v41 resolved payload tuple + v40 read adapter
  - `9434a2f5b` test(events): rollback/atomicity gate for v41 resolved outbox
  - `cf9ce1326` feat(codegen): emit v41 payloads to TypeScript with tsc round-trip

## Owned surfaces

- `substrate/feedback/migrations.py` (NEW — sole v40→v41 migration owner)
- `substrate/schemas/events.py` (v41 payload union seam; version 40→41)
- `substrate/feedback/service.py` (resolve caller full-tuple only)
- `tools/codegen/emit_types.py` (v41 registry + enum aliases + whitespace fix)
- `apps/reading/src/generated/types.ts` (regenerated; never hand-edited)
- Tests: `test_feedback_migration_{v41,kill_resume,concurrency,digest_vectors}.py`,
  `test_feedback_event_schema_v41.py`, `test_event_schema_roundtrip.py`,
  `test_feedback_event_rollback.py`, fixtures `v41_ts_roundtrip.ts`,
  helpers `_migration_crash_runner.py`, `_migration_concurrent_writer.py`.

## Gate evidence (fresh run 2026-08-29T16:25:20Z)

Commands and exit codes, verbatim:

    pytest <9 lane files> -q          → 69 passed in 27.25s        exit=0
    ruff check <12 files>             → All checks passed!          exit=0
    tools/codegen/check_staleness.py  → events OK, contracts OK    exit=0
    git diff --check                  → (silent)                    exit=0
    real-DB migration smoke           → marker completed            exit=0

Real DuckDB migration marker (seeded baseline, single `migrate_feedback_v41` run):

- phase: `completed`; `completed_at` set.
- temp/active schema digests: `9146bc64f69edc95…` (equal); rows digests: `11674785d9cb6be8…` (equal).
- Active thread survives with `entry_kind='comment'`.

What the 69 tests prove (by file):

1. `test_feedback_migration_v41.py` (11) — nine-table rebuild, D2 defaults (incl. `attempt_actual_cents=0`), malformed thread/item quarantine, aggregate cascade, overbound-Unicode-ID safe quarantine, marker completion, idempotent rerun, tamper refusal, rollback/resume.
2. `test_feedback_migration_kill_resume.py` (6) — real-process kill (exit 70) at EVERY phase boundary (started/temp_created/copied/renamed) then fresh-process resume to completed with intact digests+data; third-run no-op; baseline-drift-after-crash refuses rename and preserves everything.
3. `test_feedback_migration_concurrency.py` (3) — deterministic writer exclusion while the write flock is held; no lost rows across the race; `migration_in_progress` fail-fast with zero catalog mutation.
4. `test_feedback_migration_digest_vectors.py` (8) — golden SHA-256 vectors for `canonical_row_json`/`schema_digest`/`row_digest` (spec-derived, independently computed); DuckDB catalog-rendering determinism + golden pin.
5. `test_feedback_event_schema_v41.py` (18) — version 41 exactly once; six enums' exact strings; every payload conditional (highlight digest incl. empty-array fixture, pre-boundary cancellation, edit/branch pointers, role digests/error codes); v40 adapter selection + structural re-emit rejection.
6. `test_event_schema_roundtrip.py` (13) — all nine v41 discriminators round-trip through the `TypedPayload` union; codegen registry completeness guard; `tsc --noEmit --strict` compile round-trip of the committed TS harness.
7. `test_feedback_event_rollback.py` (3) — rolled-back transaction leaves no event AND no row; commit carries the v41 event atomically; byte-drift replay refused.
8. `test_feedback_routes.py` (2) + `test_feedback_store.py` (6) — pre-existing feedback behavior unregressed.

## Known gaps / limitations (all deliberate, on record)

1. Baseline-digest record rides in `feedback_threads_v41_quarantine` under the catch-all reason with `evidence_json.kind="baseline_rows_digest"`; audit consumers must filter on the kind marker. Cleaner home needs a spec-level marker change.
2. Schema digests hash DuckDB's catalog rendering (not spec DDL text); pinned to 1.5.4 rendering by golden vector so upgrades fail loudly, not silently.
3. Recovery runbook for a refused drift (restart-from-temp-created) is not implemented; the failure is fail-closed.
4. TS round-trip is compile-time only; Python remains the sole runtime validator.
5. `D2QueueTransitionReason`/`RoleEventReason` emitted as TS aliases but have no payload fields yet (SPR-04 runtime emission).

## Review status

- Round-1 different-lineage review (deepseek-v4-pro): **REQUEST CHANGES** — 2 P0 (dependency cascade absent; migration lock absent) + 3 P1 (map/defaults, quarantine safety, digest canonicalization). **All repaired** in `9b739a4f3` with regression tests; several repairs caught further real bugs (resume-after-rename, digest-row ordering).
- Re-review: attempted 5× on 4 lineages (deepseek-pro/flash, glm-5.3, gpt-5.6-luna) — every child dies after one empty assistant message. Diagnosed as subagent-infrastructure failure, not task failure. Probe cadence continues each heartbeat.
- **No independent ACCEPT is claimed.** Do not treat SPR-01 as accepted until a different-lineage review passes over `2817545a..cf9ce132`.

## Next wave (SPR-02 preflight, from the accepted sprint)

SPR-02 requires the completed `d2_feedback_v41` marker with matching active digests (proven above), plus SPR-01 review acceptance. Out-of-matrix legacy routes remain uncertified. Do not enable production flags, push, or merge from this lane.
