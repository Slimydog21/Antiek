# SWARM BRIEF — mimo-cc — BYOT usage/balance HTTP endpoints

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. STACKED on your round-2 BYOT usage/balance lane — the ledger + balance adapters
already exist here (read them first).

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm3/mimo-usageapi`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm3/byot-usage-api`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. Tests use TestClient/fixtures, NO live net.
  NEVER print secrets. venv: `~/Antiek/platform/.venv/bin/python`, run from worktree root.
- ruff + mypy --strict on new code.

## Context already on this branch (do NOT rebuild — reuse)
`substrate/byot_usage/` — the `ByotUsageLedger` (per-key `used_cents`/`limit_cents`/`remaining`,
keyed `(api_key_id, owner_user_id)`) and the balance adapters (DeepSeek/Kimi native, OpenAI
spend-history). Read them. Also read a sibling `interfaces/research/api/*_routes.py` for the
router + auth (owner_user_id from session) pattern.

## The sub-goal
Expose the usage ledger + balances over HTTP so the dashboard + model dropdown can show
per-key usage and remaining balance. Read the byot-onboarding spec's usage/balance + dashboard
sections IN FULL first:
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/byot-onboarding.md`

### Scope (bounded — exactly this)
Create `interfaces/research/api/byot_usage_routes.py` (register it in the app) with, scoped to the
current user's `owner_user_id`:
- `GET /settings/usage` — per-key usage snapshot (used_cents, limit_cents, remaining) for the
  user's keys.
- `POST /settings/usage/{api_key_id}/limit` — set a key's `limit_cents`.
- `GET /settings/balance/{api_key_id}` — call the appropriate balance adapter (by provider kind)
  and return the normalized balance, or `{"status":"unavailable"}` on adapter degrade.
All endpoints owner-scoped (a user never sees another user's keys → 404 on cross-user id).

### Acceptance (must pass for real)
Tests (TestClient, adapters MOCKED — no live net): `GET /settings/usage` returns the ledger
snapshot for the session user only; setting a limit is reflected in the next snapshot; `GET
/settings/balance/{id}` returns the mocked adapter's normalized balance AND returns
`status=unavailable` when the adapter degrades; a cross-user `api_key_id` → 404. Report exact pass
counts. mypy --strict clean.

### Non-goals
NO frontend/React. NO wiring the ledger into the live provider-gateway settle path (higher blast
radius — separate lane; the `record_settlement` hook stays unit-tested). NO new balance adapters.
Just the HTTP endpoints over the existing ledger + adapters.

## When done
`git add -A && git commit -m "feat(byot): usage/balance HTTP endpoints (owner-scoped)"`, then write
`DONE.md`: files, exact test command + real result, honest gaps.
