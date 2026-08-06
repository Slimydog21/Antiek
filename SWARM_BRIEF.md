# SWARM BRIEF — codex-cc — Prime Agent PrimeExecProvider adapter (default-off)

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code for the Antiek platform. This is the operator's HEADLINE enhancement — embed
PrimeIntellect prime-agent as an execution provider — done as the SUBSTRATE (adapter), gated OFF.

## Hard guardrails (violating these fails the task)
- Work ONLY inside this worktree (CWD `/tmp/antiek-swarm2/codex-prime`). NEVER `cd` out, NEVER
  touch `~/Antiek/platform` or another worktree, NEVER modify `main`.
- NEVER `git push`. Commit locally to `swarm2/prime-exec-provider` only.
- NO stub-theater. If genuinely blocked, write `BLOCKED.md` and stop — never fake green.
- Tests must NOT require the real `prime-agent` binary or any network — mock the subprocess with
  a fake that emits canned JSONL. venv: `~/Antiek/platform/.venv/bin/python`, run from worktree root.
- Match house style (read neighbors). ruff + mypy --strict on new code.

## The sub-goal
Add a `PrimeExecProvider` that implements the EXISTING `RemoteExecProvider` Protocol so Antiek
CAN run research fan-out in a prime-agent session — built but DEFAULT-OFF and NOT wired to
dispatch. Read this spec IN FULL first:
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/prime-agent-embed.md`

### Scope (bounded — exactly this)
1. Read `runtime/remote_exec/provider.py` (the `RemoteExecProvider` Protocol) and its sibling
   `runtime/remote_exec/daytona.py` to match the exact interface + error contract.
2. Create `runtime/remote_exec/prime_exec.py` — `PrimeExecProvider` implementing the Protocol by
   spawning `prime-agent --mode rpc` as a per-session subprocess and speaking its JSONL command
   protocol (prompt/steer/follow_up + a typed event stream). Isolation is the caller's job
   (documented). The provider is enabled ONLY when an env flag (e.g. `ANTIEK_PRIME_EXEC_ENABLED`)
   is set; unset ⇒ the factory does NOT offer it (default-off).
3. RE-AFFIRM the standing REJECTs in a module docstring + code: prime-agent is a research-fanout
   RemoteExecProvider ONLY — NEVER a dispatch/inference provider, NEVER `prime rl run`. Do NOT
   register it in any dispatch provider list.

### Acceptance (must pass for real)
Tests (subprocess mocked — a fake emitting canned JSONL, NO real binary/network): the provider
satisfies the `RemoteExecProvider` Protocol; a run drives the fake subprocess and parses its
event stream into the Protocol's result type; JSONL is split on LF only (CR-stripped); a
subprocess error maps to the Protocol's failure contract; with the flag unset the factory does
NOT return a PrimeExecProvider. Report exact pass counts. mypy --strict clean on the new file.

### Non-goals (do NOT do these)
NO wiring into `cascade_routes` / no activation. NO ratification bypass (`ANTIEK_RLM_RATIFIED`
is operator-only). NO dispatch-provider registration. NO kernel-skill packaging (separate lane).
Just the provider class behind the existing Protocol + tests.

## When done
`git add -A && git commit -m "feat(remote-exec): PrimeExecProvider adapter (default-off, research-fanout only)"`,
then write `DONE.md`: files, exact test command + real result, honest gaps.
