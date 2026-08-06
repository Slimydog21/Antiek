# SWARM BRIEF — mimo-cc — BYOT per-key usage ledger + balance adapters

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. This worktree is STACKED on the round-1 BYOT lane (per-user scoping + preset
provider catalog already exist here — read them first).

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm2/mimo-byot`). NEVER `cd` out, NEVER touch
  `~/Antiek/platform`/another worktree/`main`. NEVER `git push`. Commit to `swarm2/byot-usage-balance`.
- NO stub-theater. If blocked, write `BLOCKED.md` and stop. NO live/paid network — tests use
  `httpx.MockTransport`/fixtures. NEVER print secrets. venv: `~/Antiek/platform/.venv/bin/python`.
- Match house style. ruff + mypy --strict on new code. Run tests from worktree root.

## Context already on this branch (do NOT rebuild)
`runtime/byot_provider_catalog.py` (presets incl. deepseek/kimi/zhipu_glm/mimo/xai), per-user
`owner_user_id` scoping in the byok store, `settings_models_admin.py`. Read them.

## The sub-goal
Complete the "see usage + remaining balance per key" backend: (A) a per-key USAGE LEDGER fed by
real spend-settle events, and (B) BALANCE adapters for the three provider classes. Read this spec
IN FULL first (usage-ledger + balance sections):
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/byot-onboarding.md`

### Scope (bounded — exactly this)
1. **Usage ledger.** Find the spend ledger + its settle events (grep `research_spend`,
   `ResearchSpendLedger`, `budget_ledger`, `settle`). Add a per-key ledger keyed by
   `api_key_id` (+ `owner_user_id`) that accumulates `used_cents` from settle events and holds a
   user-set `limit_cents`; expose a read: (used_cents, limit_cents, remaining) per key.
2. **Balance adapters (3 classes).** A small `BalanceAdapter` interface + concrete adapters:
   - DeepSeek: `GET https://api.deepseek.com/user/balance` → total/granted balance.
   - Kimi/Moonshot: `GET https://api.moonshot.ai/v1/users/me/balance` → available/cash.
   - Spend-history class (OpenAI): remaining = user budget − spend (no live call needed; compute
     from the usage ledger). 
   Each adapter DEGRADES to `unavailable` on schema mismatch/HTTP error (never crashes the caller).

### Acceptance (must pass for real)
Tests (MockTransport/fixtures): the usage ledger accumulates `used_cents` from a fake settle
event and computes remaining vs `limit_cents`; DeepSeek + Kimi adapters parse fixture JSON into a
normalized balance; a malformed response yields `unavailable` (not an exception). Report exact
pass counts. mypy --strict clean on new files.

### Non-goals
NO frontend/dropdown UI. NO OAuth. NO all-six providers (DeepSeek + Kimi + the OpenAI
spend-history pattern is enough). NO changes to the round-1 scoping/preset code except additive.

## When done
`git add -A && git commit -m "feat(byot): per-key usage ledger + balance adapters"`, then write
`DONE.md`: files, exact test command + real result, honest gaps.
