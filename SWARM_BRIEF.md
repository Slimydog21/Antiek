# SWARM BRIEF — mimo-cc — wire the usage ledger into the live settle path

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. STACKED on your round-2 usage-ledger lane — the `ByotUsageLedger` +
`record_settlement` hook already exist here (read them first).

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm4/mimo-settle`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm4/usage-settle-wiring`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. Tests use fixtures/in-process, NO live net.
  NEVER print secrets. venv: `~/Antiek/platform/.venv/bin/python`, run from worktree root.
- ruff + mypy --strict on new code. This touches a shared settle path — change the MINIMUM.

## The sub-goal
Make the per-key usage ledger actually POPULATE from real spend by calling its `record_settlement`
hook at the provider settle site — the gap your round-2 lane flagged. Read the byot-onboarding
spec's usage section IN FULL first:
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/byot-onboarding.md`

## Context already on this branch (do NOT rebuild)
`substrate/byot_usage/` — `ByotUsageLedger.record_settlement(api_key_id, owner_user_id, cents)`.
Find the provider settle site (grep `ResearchProviderGateway`, `def settle`, `record_settlement`,
`ResearchSpendLedger`, the per-dispatch cost reconciliation).

### Scope (bounded — exactly this; MINIMAL, defensive)
At the existing settle/reconcile site (where a dispatch's real cost is known), ALSO call
`ByotUsageLedger.record_settlement(...)` for the key that was used — but:
- resolve `api_key_id` + `owner_user_id` from the dispatch context (if not resolvable, skip — do
  NOT invent);
- wrap the call so a ledger failure NEVER breaks the settle path (try/except + log, defensively
  isolated — mirror how other audit hooks are isolated);
- do NOT change the existing settle math or the ResearchSpendLedger behavior.

### Acceptance (must pass for real)
Tests: a fake settle event with a resolvable key records `used_cents` in the ledger; a settle
event with NO resolvable key is skipped (ledger untouched, no crash); a ledger-write exception is
swallowed and the settle path still completes (defensive isolation). Existing settle/gateway tests
still pass. Report exact pass counts. mypy --strict clean.

### Non-goals
NO frontend. NO change to settle math / ResearchSpendLedger. NO new endpoints (those are #2985).
Just the defensive `record_settlement` call at the settle site + tests.

## When done
`git add -A && git commit -m "feat(byot): populate usage ledger from the settle path (isolated)"`,
then write `DONE.md`: files, exact test command + real result, honest gaps.
