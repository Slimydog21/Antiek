# Research brief wiring handoff

The package is additive because these call sites are frozen to this sprint.

- `substrate/engagement_spine/spawn.py:83` (`spawn_from_highlight`): for a
  non-trivial highlight launch, create/project a `ResearchBrief`, collect edits,
  call `approve`, then require `run_token` before changing the reserved spawn to
  runnable. Preserve the selection-derived goal as the brief question.
- `substrate/midnight_oil/product_path.py:106` (`approve_price_ceiling`) and
  `substrate/midnight_oil/product_path.py:365` (`run_job_offline`): represent the
  job as `unattended=True`, copy the operator-approved ceiling into
  `price_ceiling`, and require the brief's `run_token` at the run boundary.
- `apps/reading/src/modes/ResearchWorkstation/StartResearch.tsx:160`
  (`StartResearch`, specifically `onSubmit`): non-trivial submissions should
  render the HTML brief for revise/approve before calling `submit`; pass the
  resulting run authorization through the server launch contract.

## Policy boundary

A run is non-trivial when it uses the `deep` or `wrestle` tier, fans out, or is
unattended. A one-shot `fast` answer without fan-out may skip the brief. This
keeps latency as the product for quick answers while gating material spend and
scope. Reverse this threshold if measured W0 preference/cost evidence shows
fast answers benefit enough to offset the extra interaction.

## Wave-1 compatibility

`BudgetTuple` is the documented local placeholder. Replace it with SPR-01's
`TierBudget` at this package boundary once that type lands; do not maintain two
authoritative budget shapes.
