# SPR-04 correlation_id handoff

## Round 2 sharpen

- FIX A/C: implicit inheritance is verified across direct body emits, `asyncio.create_task`, `asyncio.gather`, typed emits, a prebuilt `EventEmitter`, and the threadpool path via `asyncio.to_thread`. The live-code scan found no raw `run_in_executor` event emit site; current threadpool emit inheritance holds through `to_thread`, and remote-exec explicit `plan.correlation_id` threading remains unchanged.
- FIX D: `where-did-it-stall --correlation-id` now reports per investigation when no `--investigation-id` is supplied. Phase bookkeeping is isolated by investigation, so a phase enter in one child cannot match a phase exit in another.
- FIX E: pre-SPR-04 rows remain best-effort. Rows with no `correlation_id` still read as their own `investigation_id`; legacy fan-out parent scopes are not reconstructed. CLI help documents that limitation, and empty `--correlation-id` results print a one-line hint.
- FIX F: correlation normalization is consolidated to write-side emit paths plus the `trajectory()` backward-compat rewrite for genuinely old rows. The `Event` read-time model validator no longer fills missing correlation ids, so future writer slips remain observable.
- FIX G: reset semantics are pinned: after `correlation_context("root-X")` exits, a subsequent kwarg-less emit normalizes back to its own investigation id.
