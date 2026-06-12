# Path A — DRW gather → Loop 1 synthesis tail

**Date:** 2026-06-12
**Source spec:** ANT-DRL SPR-DRL-06
**Status:** Ratified at implementation

## Decision

Interview ratified **Path A**: DRW owns parallel gather; Loop 1 owns phases
6–9 on the **session parent** (`session_id`). One terminal spine —
``DeepResearchComplete`` on the parent, not per leaf.

## Event sequence

```
cascade.launched (session_id)
  └─ investigation.spawned_from × N (leaf investigations)
       └─ gather loop StepEvents → PromotionFunnel → graph insights
join_and_merge (link insights → sub-question nodes)
build_evidence_pack (SessionEvidencePack)
run_synthesis_tail_from_pack (session_id)
  ├─ phase 6: synthesize.requested → synthesize.delivered
  ├─ phase 7: MASTER.md + master_md_written
  ├─ phase 8: auto_patch_applied
  └─ phase 9: investigation.completed
```

## Call sites

| Module | Role |
|--------|------|
| `orchestration/cascade_session.py` | `build_evidence_pack`, `run_synthesis_tail`, `is_deep_research_complete` (parent) |
| `orchestration/loop_one/orchestrator.py` | `run_synthesis_tail_from_pack` (phases 6–9) |
| `interfaces/research/api/cascade_routes.py` | Background completion invokes synthesis runner |
| `interfaces/research/api/app.py` | Wires runner after Loop 1 handler registration |

## Rejected alternative

**Two-step UX (gather, then operator-triggered synthesize)** — rejected.
Split-brain failure mode: two terminals, one product name.

## Reconsider if

Loop 1 is deprecated and DRW owns synthesis end-to-end with the same
postcondition module — contract stays, call sites move.