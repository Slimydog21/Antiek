## Sprint SPR-01 — Handoff

### Status
DONE

### Files touched
- substrate/research_budget/__init__.py:1 — exports the canonical tier contract.
- substrate/research_budget/tiers.py:9 — adds the frozen tuple, sourced operator-tunable defaults, and import-time strict monotonicity guard.
- substrate/research_budget/run_record.py:13 — adds declaration, cumulative actuals, tri-state verdict, payload serialization, and parsing.
- substrate/research_budget/projection.py:16 — adds caller-priced conservative half/full-use cost intervals using the bench 1.25 input buffer.
- substrate/research_budget/WIRING.md:1 — records exact frozen integration needs without editing those surfaces.
- tests/test_research_budget.py:1 — adds red-proofs, exact 80%/100% boundaries, round-trip, and hand-computed projection coverage.
- HANDOFF-SPR01.md:1 — records this handoff in the required format.

### Milestones
- [x] M1: TierBudget model + canonical tiers — frozen positive tuples, sourced tunable defaults, and a tested import-time monotonicity assertion.
- [x] M2: Run-record declaration + actuals — pure cumulative accounting with within/warned/exceeded verdicts and payload round-trip.
- [x] M3: Projection bridge — pure Decimal interval using half/full utilization and cheapest/priciest declared rates.
- [x] M4: Test suite — 8 Python 3.14 tests, including assertion and boundary red-proofs.
- [x] M5: WIRING.md — three frozen call sites documented with tuple/projection API usage.

### Verification gate results
- pytest: pass — `8 passed in 0.17s`.
- mypy strict: pass — `Success: no issues found in 4 source files`.
- ruff: pass — `All checks passed!`.
- seam purity: pass — all six changed implementation/test paths are owned. The prescribed pipeline exited 0 but printed Git's aggregate `6 files changed, 275 insertions(+)` line because that line contains no path for the grep to filter; `git diff --name-only ...` independently listed only `substrate/research_budget/*` and `tests/test_research_budget.py`.

### WIRING.md entries added (frozen-file needs documented, not edited)
- interfaces/research/api/settings_budget.py → derive the estimate interval from `TIERS[research_tier]` and `project_cost(...)` with caller-supplied model prices.
- apps/reading/src/components/engagement/ResearchLaunchBudgetPanel.tsx → remove UI-owned output-token constants and display the backend-declared tuple and interval.
- substrate/midnight_oil/ceiling.py → replace research-tier multipliers with the tuple/projection default while retaining explicit approval and duration policy.

### Decisions made mid-flight
- Decision: use integer cross-multiplication for the 80% threshold / avoids float drift at the exact boundary / reverse if the contract changes from an inclusive 80% warning.
- Decision: treat exactly 100% as warned and only values over 100% as exceeded / “exceeded” means actuals surpassed a declared limit / reverse if product language defines reaching a cap as exceeded.
- Decision: use Decimal and cent-level ROUND_HALF_UP / makes the hand-computed monetary contract deterministic / reverse only if the product establishes a different currency rounding policy.

### Assumptions surfaced (rigor #1)
- The standalone sprint's quoted doctrine evidence is authoritative because `docs/deep_research_doctrine.md` is absent from this branch.
- Tier numbers are hypotheses, not measured Antiek optima; every default is marked OPERATOR_TUNABLE and W0 calibration remains pending.
- The single `token_budget` is conservatively priced once at buffered input plus output rates because the tuple does not declare an input/output split.

### Steelman of rejected alternative (rigor #2)
- Extending the existing Settings estimate API would minimize integration work because it already owns model pricing and the UI consumes its response. I still agree with the new module: the Settings surface is frozen, its prompt projection does not declare run budgets or actuals, and coupling declaration to that endpoint would prevent non-UI consumers from sharing one contract.

### Open questions discovered
- What empirical W0 curves should replace the tier hypotheses and validate doctrine invariant I-9? — W0 eval-harness owner.
- Should reaching exactly 100% remain warned or become exceeded in product copy? — campaign/product owner.

### Next sprint can start when
- Consumers can import `TierBudget`/`TIERS`; budget-to-quality validation remains explicitly pending-W0 and is not a construction blocker.
