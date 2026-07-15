# Suggested research thread cards — design evidence

Date: 2026-07-15

Branch: `goal/suggested-research-thread-cards`

Base: `goal/research-lineage-board` / PR #2428

## Product gap

`SuggestedResearch` already preserved the correct product authority: suggestions are read-only daemon output, an explicit click is the only spend, and every chase uses the existing capped launch path. Generic dashed cards made that compounding loop feel like utility chrome and had no authored visual proof.

## Design decision

- Treat each offer as an open index thread, using quiet locators and dashed boundaries that remain distinct from solid in-flight research rows.
- Preserve `could chase`, cross-research occurrence counts, questions, retrieval hints, and launch controls without inventing confidence or priority.
- Present retrieval guidance as a restrained search-lead inset, not as evidence or a completed result.
- Keep the lane's weathered-sun spine subtle; no mascot or generated art competes with questions the researcher must judge.
- At phone width, header copy and retrieval leads stack so no question or provenance is truncated.

## Proof

- Storybook: `ResearchWorkstation / Suggested research thread cards / Lane`
- Storybook: `ResearchWorkstation / Suggested research thread cards / BesideAnswer`
- Storybook: `ResearchWorkstation / Suggested research thread cards / SignedOut`
- Six LostPixel baselines cover the two primary contexts at 1280, 1024, and 768 px.
- Direct Playwright inspection covers 1280 and 390 px; both primary stories report zero direct axe violations.
- Focused tests prove rendering still causes no launch and visual locators do not change suggestion status.
