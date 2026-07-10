# Research-budget wiring (frozen surfaces)

These call sites are intentionally not edited in SPR-01.

- `interfaces/research/api/settings_budget.py::estimate_prompt_cost`: replace the
  prompt-only tier projection with `TIERS[research_tier]` plus
  `project_cost(TIERS[research_tier], declared_model_prices)`. Keep prices
  caller-supplied; return the resulting lower/upper interval through the existing
  response fields.
- `apps/reading/src/components/engagement/ResearchLaunchBudgetPanel.tsx::dispatchTierFor`:
  remove the UI-owned `expected_output_tokens` constants. Have the Settings
  response expose the declared `TIERS[research_tier]` tuple and render that
  declaration alongside the `project_cost(...)` interval.
- `substrate/midnight_oil/ceiling.py::recommend_price_ceiling`: replace
  `TIER_MULTIPLIER` as the research-intensity source with the selected
  `TIERS[research_tier]` declaration and use `project_cost(...)` as the default
  recommended ceiling. Preserve explicit operator approval and duration-specific
  policy outside the projection bridge.
