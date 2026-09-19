# Code craft — honesty contract wiring + HTML projection unify

**Date:** 2026-09-19 (Asia/Riyadh)  
**Parent tip:** `85ca2006de37b4a104646fa3e98538c99b86fc41` (#3223 Specs honesty)  
**Code before:** ~96 · **after:** ~98  
**Does not:** flip mount / Synquery / G2 / email / invent CPM.

## Forensic Code gaps (intellectually defensible)

1. **Research `artifact.html` header drift** — shipped `X-Antiek-Projection: research-artifact-html-native` while Specs (#3223) froze `X-Antiek-Html-Projection: script-free; disposition=…` for all four View HTML surfaces. Decision→implementation fidelity miss.
2. **Duplicated `_html_headers` + hardcoded strings** — notebook/deliverable/synthesis each reinvented the projection header; synthesis `?format=html` attachment omitted the projection header entirely.
3. **Honesty envelopes unguarded at builders** — Specs contract tests existed, but `website_ads_honesty` / `g2_synquery_honesty` / `capacity_exhausted_payload` could drift without failing at the source.
4. **Deepblu “private no-payout UX not productized”** — stale vs shipped create/invite/invitee/settings notices (`PRIVATE_ECON_COPY`); Code residual was catalog honesty, not missing chrome.

## What shipped

- `html_projection_response_headers()` on `substrate.contracts.anti_ek_honesty`
- Research / synthesis / deliverable / notebook routes consume the helper
- Self-assert at honesty builders (fail closed on envelope drift)
- Research route test expects tip-honest Html-Projection header
- Deepblu remap: private no-payout UX marked **productized**

## Grade

| Surface | Before | After |
|---------|-------:|------:|
| Code | 96 | **98** |
| Composite | ~98.23 | ~98.38 → still **~98** |

Residual Code →100: broader OpenAPI response models; flaky shard tests (hathitrust / fills timing) not inventing product. Next: **TPuf ~95** without mount flip.
