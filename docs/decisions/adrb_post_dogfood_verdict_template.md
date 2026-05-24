# ADRB — post-dogfood verdict (TEMPLATE)

> Copy to `docs/decisions/adrb_post_dogfood_verdict.md` and fill in.
> This is the artifact that survives turnover: the answer to "why
> does Antiek have / not have a Deep Research Bridge?"

**Date completed.** YYYY-MM-DD.
**Spec.** `~/specs/antiek-deep-research-bridge/index.html`.
**Operator log.** `runs/adrb/operator-log.md`.
**Metrics.** `runs/adrb/dogfood_metrics.md` (from `dogfood-report`).

## The 5 projects
- 1. ____  - 2. ____  - 3. ____  - 4. ____  - 5. ____

## Verdicts

### Mode A (outline writing)
**SHIP / KILL / ITERATE.** Evidence:
- Drafts exported: ___ / 5.
- Drafts operator would send / publish: ___.
- Most common failure (1 sentence): ____.
If KILL — what is salvageable? If ITERATE — 3 sharpest questions.

### Mode B (gap-finder + cascaded prompts)
**SHIP / KILL / ITERATE.**
- S3 gate: would-run % across all 5 = ___% (target ≥ 60%).
- Cascade depth actually run: ___ iterations.
- Did paste-back-and-re-cascade close the loop on real research?
- Did the cascade cause prompts you wouldn't have run otherwise?
If KILL — salvageable? If ITERATE — 3 sharpest questions.

## What I was surprised by
- ____  - ____  - ____

## Proposed Wave 4 sprints (or "no Wave 4")
From `wave4_candidates.md`:
- SPR-NN-____ — one-paragraph goal.

## Operator-only next-step gates
- [ ] Onboard a second user? (SHIP on a mode + §9.0 legal gate closed
      + specific second user named).
- [ ] Promote pastes to graph nodes by default? (insights already
      promote via SPR-04 patch; pastes-as-nodes is the deeper move).
- [ ] Open beta? (needs auth, abuse policy, paste-content sanitation).

## Sign-off
Operator: _________  Date: _________
