# SWARM BRIEF — mimo-cc — wire ExecutionBackend into the cascade (behavior-neutral)

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. STACKED on the ExecutionBackend seam lane — `runtime/exec_backend/` already exists here.

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm5/mimo-cascade`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm5/cascade-wiring`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. venv: `~/Antiek/platform/.venv/bin/python`,
  run tests from worktree root. ruff + mypy --strict on new code.
- **THIS TOUCHES THE PRODUCTION RESEARCH LAUNCH PATH. The DEFAULT behavior (flag unset) MUST be
  BYTE-IDENTICAL to today.** Change the minimum. When in doubt, keep the old path and add the new
  one behind the flag.

## Context already on this branch (do NOT rebuild — activate it)
`runtime/exec_backend/` — the `ExecutionBackend` Protocol + `LocalProcessBackend` (built but
UNPLUGGED). The cascade launch site constructs `HostLocalRunner` directly — find it (spec says
`cascade_routes.py:1254`; grep `HostLocalRunner(` to confirm the exact line). Read the spec IN FULL:
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/sandbox-execution-seam.md`

## The sub-goal
Make the ExecutionBackend seam REACHABLE from the cascade — behind a default-off flag, so agents
CAN run through the abstraction, but today's behavior is unchanged until the operator flips it.

### Scope (bounded — exactly this)
1. Add a `build_execution_backend()` factory in `runtime/exec_backend/` (if not present) that
   returns a `LocalProcessBackend` by default, selected by env (e.g. `ANTIEK_EXEC_BACKEND`, unset →
   the LOCAL default). Reconcile the factory signature with what the cascade call site passes
   (the spec flags `seal_on_complete` / `retrieval_substrate` kwargs the factory must accept or the
   runner must adapt) — MINIMALLY.
2. At the cascade launch site: when the flag is SET, route through `build_execution_backend`; when
   UNSET (default), construct `HostLocalRunner` EXACTLY as today. A one-line branch, not a rewrite.

### Acceptance (must pass for real)
Tests: with the flag UNSET, the existing `HostLocalRunner` path is used and behaves exactly as
before (assert the runner type / no new backend constructed); with the flag SET,
`build_execution_backend` is invoked and returns a `LocalProcessBackend`; the factory default is
`LocalProcessBackend`. Existing cascade/runner tests still pass. Report exact pass counts. mypy
--strict clean.

### Non-goals
NO DockerBackend/remote selection (Local only). NO behavior change when the flag is unset. NO
cascade logic change beyond the runner-construction branch. NO DuckDB→Postgres. Just the factory +
the flagged branch + tests.

## When done
`git add -A && git commit -m "feat(exec-backend): reachable from cascade behind default-off flag"`,
then write `DONE.md`: files, exact test command + real result, and CONFIRM default behavior is unchanged.
