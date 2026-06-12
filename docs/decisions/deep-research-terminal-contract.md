# DeepResearchComplete terminal contract

**Date:** 2026-06-12
**Source spec:** ANT-DRL (`docs/htmlspec/deep-research-loop/`, SPR-DRL-01)
**Status:** Ratified at implementation

## Problem

Loop 1 (Ask) and DRW (Cascade) shared a product name but not a terminal
contract. Loop 1 ends at `synthesize.delivered` + phases 6–9 +
`investigation.completed`. DRW's prod factory (`cascade_routes._research_loop_factory`)
still returned `make_demo_loop(steps=3)`, which reaches runner `DONE` without
synthesis — split-brain.

## Contract

An investigation is **DeepResearchComplete** when all of the following hold:

1. **Phase 6** — `synthesize.delivered` in trajectory with
   `constraint_loop_status` ∈ {`single_pass`, `passed`} and non-vacuous
   falsifications (or `insufficient_evidence` escape hatch per H2.5).
2. **Phase 7** — `master_md_written` event or `MASTER.md` on disk above floor.
3. **Phase 8** — `auto_patch_applied` with patched domains, skill-file growth,
   or `insufficient_evidence` no-op pass.
4. **Phase 9** — `PhaseLog.assert_ready_for_completion` (phases 6–8 verified).
5. **Terminal event** — `investigation.completed` in trajectory (retrospective /
   session checks only; Loop 1 asserts 1–4 immediately before emitting 5).

Implementation: `orchestration/invariants/deep_research_complete.py`.

## Call sites

| Module | When |
|--------|------|
| `orchestration/loop_one/orchestrator.py` | Before `investigation.completed` (`require_terminal_event=False`) |
| `orchestration/cascade_session.py` | `is_deep_research_complete()` per leaf |

## Rejected alternative

**Path B (honest fork):** deprecate Loop 1, perfect DRW-only terminal.
Rejected at spec interview — split-brain remains the named waste mode until
convergence (SPR-DRL-06).

## Reconsider if

Loop 1 is deprecated and DRW owns synthesis end-to-end with the same
postcondition module — contract stays, call sites move.