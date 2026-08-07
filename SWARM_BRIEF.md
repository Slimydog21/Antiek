# SWARM BRIEF — deepseek-cc — DockerBackend (ExecutionBackend Stage 1)

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. STACKED on the ExecutionBackend seam lane — the Protocol already exists here.
(A prior agent timed out on this lane with zero output; you are building it fresh.)

## Hard guardrails (touch ONLY new files)
- Work ONLY inside this worktree (`/tmp/antiek-swarm4b/ds-docker`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm4b/docker-backend`.
- **Your work is a NEW file `runtime/exec_backend/docker_backend.py` + a NEW test file. The ONLY
  allowed change to an existing file is adding `DockerBackend` to the backend registry + `__all__`.**
  Do NOT modify `local_process.py`, `interface.py`, or the Protocol.
- NO stub-theater. If you produce nothing you fail — deliver the backend + tests or write
  `BLOCKED.md` with a real blocker. venv: `~/Antiek/platform/.venv/bin/python`, run from worktree root.
- ruff + mypy --strict on new code.

## Context already on this branch (do NOT rebuild — implement against it)
`runtime/exec_backend/interface.py` — the `ExecutionBackend`/`Workspace` Protocol
(`create(profile, limits, net_policy) -> Workspace`; `Workspace.exec(argv, timeout, ...) ->
ExecResult{exit_code, stdout, stderr, duration_ms}`; `put_file`/`get_file`; `destroy()`) and
`local_process.py` (`LocalProcessBackend`). READ both first and match the EXACT interface + error
contract.

## The sub-goal
Add a `DockerBackend` implementing the SAME Protocol — one container per workspace, non-root,
read-only rootfs + tmpfs scratch, job dir mounted, mandatory `exec` timeout returning a structured
`ExecResult`. Read this spec section IN FULL first (Stage 1):
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/sandbox-execution-seam.md`

### Scope (bounded — exactly this)
`runtime/exec_backend/docker_backend.py` — `DockerBackend`/`DockerWorkspace` via `subprocess` to
the `docker` CLI (unless the `docker` Python SDK is already a dep — check `pyproject.toml`). The
`docker` client must be INJECTABLE so tests can mock it. `net_policy`: `deny_all` → `--network
none`; `allow_all` → default. Mandatory `exec` timeout kills the container step → structured
timeout `ExecResult` (no hang). `destroy()` removes the container + workspace dir.

### Acceptance (must pass for real — Docker MOCKED where absent)
Tests with the docker client MOCKED/injected: Protocol conformance; `exec` builds the right
`docker run` invocation with the timeout + `--network` flags; a timeout yields a structured result;
`net_policy=deny_all` → `--network none`; `destroy` removes the container. Add ONE real end-to-end
test guarded by skip-if-docker-unavailable. Report exact pass counts + whether the real-Docker test
ran or SKIPPED. mypy --strict clean.

### Non-goals
NO gVisor/Kata/Firecracker/E2B. NO cascade wiring. NO change to `local_process.py`/`interface.py`.
Just `docker_backend.py` + registry entry + tests.

## When done
`git add -A && git commit -m "feat(exec-backend): DockerBackend (Stage 1)"`, then write `DONE.md`:
files, exact test command + real result (paste the pytest summary), whether real-Docker ran/skipped.
