# Reviewer pass (htmlspec Phase 4)

Date: 2026-06-02. Persona: generalPurpose adversarial read.

## Wontfix (recorded)

- **Master spec five-value cards:** Glossary + sprint pages carry rigor; duplicating full cards on `index.html` would bloat the dashboard. Executors read per-sprint rigor blocks.

## Fixed from review

- **SPR-03 acceptance/rigor mismatch:** Milestone criteria now require kwargs spy on `dispatch` and `render_full_prompt`, not JSON shape alone.
- **Frontend auto-decompose UX contract:** `CascadeProposal.test.tsx` now
  asserts the Research door calls `createPlan` with exactly `{ problem }` and
  no own `sub_questions` key, including `[]`. This proves the UI exercises the
  backend auto-decompose branch instead of silently taking the manual branch.

## Residual gaps (executor backlog)

1. Add CI milestone (optional SPR-09 or extend SPR-06) wiring `repro` + `audit` into pytest/CI.
2. Replace machine-specific paths in brief with relative paths when sharing repo-only.
