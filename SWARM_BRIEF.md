# SWARM BRIEF — codex-cc — BYOT backend (per-user scoping + provider presets)

You are an autonomous coding agent. Execute this ONE bounded sub-goal completely, in THIS
worktree only. This is real production code for the Antiek platform.

## Hard guardrails (violating these fails the task)
- Work ONLY inside this worktree (your CWD: `/tmp/antiek-swarm/codex-byot`). NEVER `cd` out,
  NEVER touch `~/Antiek/platform` or any other worktree, NEVER checkout/modify `main`.
- NEVER run `git push`. Commit locally to the current branch (`swarm/byot-backend`) only.
- NO stub-theater. If a piece is genuinely blocked, write `BLOCKED.md` explaining exactly why
  and stop — do NOT fake a passing test or a hollow implementation.
- Label any live/paid/network behavior as NOT RUN; tests must use fakes/`httpx.MockTransport`,
  never real API calls. NEVER print secret values.
- Match house style: read 2-3 neighboring files first; the repo uses `ruff` + `mypy --strict`
  on new code + `pytest`. Python venv: `~/Antiek/platform/.venv/bin/python`.
- Run tests from THIS worktree root: `~/Antiek/platform/.venv/bin/python -m pytest <files> -q`.

## The sub-goal
Extend the EXISTING single-tenant BYOK substrate so (a) a user API key of a preset provider
kind does NOT land `BLOCKED_UNKNOWN_PRICING`, and (b) keys/models are scoped per user with a
delete path. Full design + verified anchors: read this spec IN FULL first:
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/byot-onboarding.md`

### Scope (bounded — do exactly this, nothing more)
1. **Preset provider-kind catalog.** Find the current provider-kind options + pricing/route
   authority (grep: `KIND_OPTIONS`, `provider_route_authority`, `BLOCKED_UNKNOWN_PRICING`,
   `settings_models_admin`, `runtime/byok`). Add preset kinds with `base_url` + a pricing
   catalog row for: **deepseek** (`api.deepseek.com`, models deepseek-chat / deepseek-reasoner
   — treat "V4 Pro"/"V4 Flash" as two selectable model-id rows), **moonshot/kimi**
   (`api.moonshot.ai`), **zhipu/glm** (`open.bigmodel.cn` or z.ai), **xiaomi/mimo**, **xai**
   (`api.x.ai`). All are OpenAI-compatible, so reuse the existing `openai_compat` provider
   path — you are adding catalog/pricing entries so a user key of these kinds is route-eligible.
2. **Per-user scoping.** Add a `user_id` to the user-model record + per-user byok cred
   namespace so two users' keys/models are isolated. Add a **delete** path (the byok store
   currently has none — documented orphaned-ciphertext limitation).

### Acceptance (must pass for real)
Write tests proving: a preset kind resolves to a known price row (not BLOCKED); a user key of a
preset kind is route-eligible; two users' models/creds are isolated by `user_id`; delete removes
a cred. Existing `settings_models`/byok tests must still pass. Report exact pass counts.

### Non-goals (do NOT do these — separate lanes)
NO OAuth of any kind. NO frontend/React. NO usage/balance ledger. NO Grok device-code. Just
presets + per-user scoping + delete, with tests.

## When done
`git add -A && git commit -m "feat(byot): per-user scoping + preset provider kinds"`, then write
`DONE.md`: what you built (files), the exact test command + real result, and any honest gaps.
