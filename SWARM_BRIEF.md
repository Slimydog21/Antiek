# SWARM BRIEF — deepseek-cc — style-wheel HTTP API + per-user persistence

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. STACKED on the forkable-style-system lane — `services/html_projection/styles.py`
already exists here (read it first).

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm2/deepseek-stylapi`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm2/style-wheel-api`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. Tests use fixtures/TestClient, no live net.
  venv: `~/Antiek/platform/.venv/bin/python`, run from worktree root. ruff + mypy --strict on new code.

## Context already on this branch (do NOT rebuild)
`services/html_projection/styles.py`: `ProjectionStyle`, `StyleRegistry`, `validate_style`,
`default_registry`, `BUILTIN_STYLES`, and `renderer.restyle_artifact(html, ctx, *, style=)`.
These are the backend primitives — you are adding the HTTP API + persistence over them.

## The sub-goal
Expose the "wheel of styles" as an API: list styles, create/fork a style (validated), delete a
fork, and regenerate an artifact in a chosen style. Read this spec IN FULL first (section 5B):
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/doc-to-html-and-style-wheel.md`

### Scope (bounded — exactly this)
1. Endpoints (find the app/router pattern, e.g. `app.py`, existing `*_routes.py`):
   - `GET /styles` — builtins + the current user's forked styles (the wheel).
   - `POST /styles` — create/fork: body → `ProjectionStyle(builtin=False)` → `validate_style`
     (rejects unsafe CSS / bad slug) → persist for this user.
   - `DELETE /styles/{name}` — forks only (builtins non-removable → 409).
   - `GET /artifacts/{id}/render?style=<name>` — load the artifact's stored HTML, call
     `restyle_artifact`, return the re-projected HTML. (No model call — deterministic.)
2. Per-user style persistence: a small table/store keyed by `user_id` for forked styles; the
   `default_registry()` builtins are always present + a user's forks layered on top per request.

### Acceptance (must pass for real)
Tests (TestClient): create a fork → it appears in `GET /styles`; render an artifact in a style →
returns HTML whose `<style>` block differs from default while the data island is unchanged;
delete a fork removes it; deleting/overriding a builtin → 409; POST with unsafe CSS
(`@import`/`javascript:`) → 4xx (validation). Report exact pass counts.

### Non-goals
NO React/frontend wheel UI. NO generic upload. NO changes to `styles.py`/`renderer.py` except
additive if strictly needed. Just the API + persistence + tests.

## When done
`git add -A && git commit -m "feat(styles): style-wheel API + per-user fork persistence"`, then
write `DONE.md`: files, exact test command + real result, honest gaps.
