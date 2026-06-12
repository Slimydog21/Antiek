# htmlspec-2 — Cycle 2 sharpen (SPR-DRL-09)

**Date:** 2026-06-12  
**Input:** `tribunal-cycle-2-synthesis.md` (egghead-1)  
**Output:** `sprint-09-dogfood-readiness.html` + `index.html` patch via `_generate.py`

## Scope ratified

| In scope (SPR-DRL-09) | Deferred |
|-------------------------|----------|
| Pack fidelity E2E (`doc-url-*` not `doc-gather-*`) | Full HTTP TestClient cascade→synthesis profile |
| Insight metadata bridge (promotion → pack) | Live Parallel in CI |
| Parent terminal observability (no silent synthesis fail) | Exa (SPR-DRL-10) |
| P-17 harness row + `canonical_verify` | Automated 10-session dogfood |
| Operator smoke checklist doc | Browserbase |

## Open question closed

**Pack E2E only vs full HTTP cascade?** → **Pack E2E + parent observability** this sprint. HTTP profile only if smoke DRW #1 surfaces HTTP-only gap.

## Movability audit (rigor cards)

- Intellectual honesty: thin-pack and silent synthesis listed as Not proved until smoke.
- Fairness: full HTTP E2E steelmanned and rejected for this cycle.
- Rigor: P-17 command is falsifiable pytest row.
- Diligence: points at `build_session_evidence_pack` placeholder path and `_run_to_completion`.
- Defensibility: tribunal decision log entries in index.html.

## Next phase

**exec-2** — grind `sprint-09-dogfood-readiness.html` per caffenagent SKILL.md (≥2 rounds, merge-on-green).