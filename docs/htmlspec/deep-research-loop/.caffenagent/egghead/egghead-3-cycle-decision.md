# Egghead₃ — Cycle 2 decision (ANT-DRL exec-2)

**Date:** 2026-06-12  
**Thesis under review:** Did exec-2 deliver SPR-DRL-09 at James Hawkins engineering bar — pack `doc-url-*` fidelity, parent-terminal observability, P-17 harness, and operator smoke checklist — without scope creep?

**Binding context:** Cycle-2 tribunal (`tribunal-cycle-2-synthesis.md`) required Tier A engineering before *trusted* prod dogfood. Excluded: full HTTP cascade E2E, live Parallel in CI, Exa (SPR-DRL-10).

## Evidence reviewed

| Surface | Finding |
|---------|---------|
| SPR-DRL-09 M1–M5 | All five milestones implemented; `state.json` round 2 with sharpen |
| P-17 | `tests/test_drw_pack_fidelity.py` — 3 tests green; pack yields `doc-url-*` under mocked Parallel + ingest |
| Harness | `./scripts/canonical_verify.sh deep-research` → `CANONICAL_VERIFY_OK` (P-11..P-17) |
| hardenx-2 | `hardenx --strict .` — LOW band, 0 REAL, 11 advisory |
| Synthesis tail wiring | `set_synthesis_tail_runner` registered in `interfaces/research/api/app.py` — not a dead code path |
| Merge state | HEAD still `bfed09d`; SPR-DRL-08/09 diff uncommitted on working tree |
| Operator proof | Smoke DRW #1 **not run**; live Parallel index **not measured** |

## Milestone audit (SPR-DRL-09)

| # | Title | Verdict | Notes |
|---|-------|---------|-------|
| 1 | Pack fidelity E2E | **pass** | Hermetic `test_drw_pack_fidelity.py`; fails on placeholder-only packs |
| 2 | Insight metadata bridge | **pass** | `_promotion_metadata()` → `source_document_id` on ingested insights |
| 3 | Parent terminal observability | **pass** | `cascade.merge_failed` / `cascade.synthesis_tail_failed`; `completion_status()`; `_run_to_completion` audited |
| 4 | P-17 harness | **pass** | `PLATFORM_EXEC_MATRIX` + `canonical_verify.sh deep-research` |
| 5 | Operator smoke checklist | **pass** | `docs/decisions/deep-research-smoke-checklist.md` — parent terminal, pack audit, G2 parallel |

## Five-values bar

| Value | Assessment |
|-------|------------|
| Intellectual honesty | Thin-pack and silent synthesis explicitly **Not proved** until smoke DRW #1; hermetic mocks labeled honestly |
| Fairness | Full HTTP cascade E2E steelmanned and deferred per spec — not smuggled as "done" |
| Rigor | Mechanical gates green; adversarial sharpen round on session status HTTP fields |
| Diligence | Read-before-write on pack builder fallback; summary note removed when ingest succeeds |
| Defensibility | Handoff + smoke checklist survive turnover; tribunal survivors honored |

## Strongest remaining objection

Hermetic fidelity ≠ prod Parallel index fit. Mock ingest proves the **bridge**; it does not prove operator query shapes return promotable URLs or that synthesis quality is acceptable. That is correctly gated to smoke DRW #1 — but it means confidence stays **moderate**, not high.

## Residual risks

1. **Unmerged diff** — `bfed09d` + local SPR-DRL-08/09; prod unchanged until PRcrouch.
2. **Smoke DRW #1 not executed** — parent `investigation.completed` + `doc-url-*` on live session unverified.
3. **Parallel index blind spots** — operator query coverage unknown (low confidence).
4. **htmlspec index lag** — `index.html` / `_generate.py` still mark SPR-DRL-09 `pending` despite exec-2 done (cosmetic; regenerate on memento).

## Open questions

1. Does smoke DRW #1 reach `deep_research_complete: true` with `synthesis_tail_error: null` on first real question?
2. Does G2 counsel packet dispatch proceed in parallel (tribunal binding — not blocked by DRW)?
3. If smoke fails on thin pack, is failure mode clustered enough to warrant htmlspec-3 wave vs point fix?

## Verdict

```json
{
  "verdict": "proceed-prcrouch",
  "confidence": "moderate",
  "residualRisks": [
    "SPR-DRL-08/09 uncommitted; prod unchanged until merge",
    "Smoke DRW #1 not run — live parent terminal + pack fidelity unproved",
    "Parallel index fit for operator queries — low confidence",
    "Full HTTP cascade→synthesis profile still deferred"
  ],
  "openQuestions": [
    "Smoke DRW #1 parent terminal + doc-url-* on real session",
    "G2 counsel dispatch in parallel track",
    "Clustered failure modes post-smoke → next htmlspec wave or point fix"
  ]
}
```

**Rationale:** Tier A (SPR-DRL-09) is complete at the engineering bar the tribunal set. Further engineering without operator smoke risks base-rate churn (tribunal base-rate lens). Next binding step per Cycle-2 DAG is **Tier B: PRcrouch** → prod `ANTIEK_DRW_GATHER=parallel` → **Tier C: smoke DRW #1** per checklist. Do **not** run sessions 2–10 until smoke green.

**Rejected alternatives:**
- `loop-full-cycle` — no load-bearing open question requires another htmlspec→exec wave *before* ship; smoke outcomes should inform Cycle 3 if needed.
- `done-no-ship` — tribunal explicitly closed cycle-1 `done-no-ship`; engineering slice is done; deferring merge repeats the incentive failure the tribunal flagged.

## Operator next actions (ordered)

1. **`/PRcrouch`** — merge `bfed09d` + SPR-DRL-08/09 to `main`, deploy substrate.
2. Prod env: `ANTIEK_DRW_GATHER=parallel`; rotate `PARALLEL_API_KEY` if ever pasted in chat.
3. **Smoke DRW #1** — `docs/decisions/deep-research-smoke-checklist.md`.
4. **G2 counsel** — parallel track, not blocked by DRW.
5. **`/memento`** after PRcrouch — tattoo cycle-2 closure + regenerate htmlspec index (SPR-DRL-09 → done).