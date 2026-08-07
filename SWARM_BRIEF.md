# SWARM BRIEF — deepseek-cc — agent coding kernel-skills (DuckDB / Python / Processing)

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. Executes the operator's "let research agents write code to mine + sculpt data" ask.

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm4/deepseek-skills`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm4/agent-kernel-skills`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. venv: `~/Antiek/platform/.venv/bin/python`,
  run tests from worktree root. ruff + mypy --strict on new code. Tests must NOT require a live
  prime-agent binary, a GPU, or network — pure-Python skill functions tested directly.

## The sub-goal
Package the agent CODING surface as reusable, typed "kernel skills" a research agent can call to
mine/sculpt data: (1) build/query a **DuckDB** store, (2) run **Python data analysis**, (3) emit a
**Processing/p5-style** visual sketch that lands as an HTML asset. Read this spec IN FULL first
(the kernel-skill packaging section):
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/prime-agent-embed.md`

### Scope (bounded — exactly this)
Create `substrate/agent_skills/` with a small skill registry + 3 skills, each a typed function +
a SKILL.md-style docstring/manifest:
1. **duckdb_store** — create an ephemeral DuckDB db, run SQL (create tables, insert, query),
   return typed rows; used to store quantitative data an agent mines. (DuckDB is already a dep.)
2. **py_analysis** — run a bounded Python analysis over a dataset (e.g. a safe eval-free helper
   that computes summary stats / aggregations with the stdlib + whatever is already a dep); return
   structured results. Keep it dependency-light (do NOT add pandas if not already a dep — check).
3. **sketch_svg** — a Processing/p5-inspired DETERMINISTIC generative-visual helper that emits an
   SVG (script-free) suitable for embedding in an Antiek HTML asset (must pass the existing
   `services/html_projection/gate` zero-script check — reuse it to validate output).

### Acceptance (must pass for real)
Tests: duckdb_store round-trips a create/insert/query; py_analysis returns correct summary stats
on a fixture dataset; sketch_svg emits deterministic SVG that PASSES `gate.find_violations` (no
script); the registry lists all 3 skills with their manifests. Report exact pass counts. mypy
--strict clean.

### Non-goals
NO prime-agent binary integration (skills are callable stand-alone; wiring them into a
prime-agent kernel is a later lane). NO new heavy deps (pandas/matplotlib) unless already present
— check `pyproject.toml` first. NO AI image/video. NO frontend. Just the 3 skills + registry + tests.

## When done
`git add -A && git commit -m "feat(agent-skills): DuckDB/Python-analysis/Processing-SVG kernel skills"`,
then write `DONE.md`: files, exact test command + real result, honest gaps.
