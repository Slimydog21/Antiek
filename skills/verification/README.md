# skills/verification/

How to verify specific claim classes. The
deterministic-rubric-plus-judged-rubric combinations applied by the
constraint middleware, captured as reusable artifacts.

## Examples

- `verify-quantum-hardware-claims/` — Coherence time, qubit count,
  gate fidelity claims.
- `verify-sovereign-fund-portfolio/` — Portfolio composition,
  position size, holding period claims.
- `verify-hiring-velocity-claims/` — Team headcount, hiring rate,
  attrition rate claims.

## Why captured as skills

In the prior Researchmaxx, verification logic was embedded in role
prompts. Promoting it to versioned skills means:

- The same verification logic is consistent across investigations.
- Verification quality is measurable (backtest correlation per skill
  version).
- Updating verification policy is one place to edit, not many prompts.

See architecture_notes §3.2.
