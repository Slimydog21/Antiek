# Runbooks Index

Quick-reference for the operator (and future agents). Each runbook is
self-contained; jump straight to the one matching your task.

| If you're trying to… | Read this |
|---|---|
| Go from zero to a working `api.antiek.ai` for the first time | `first-deploy.md` |
| Ship a code change after a `git push` | `code-update.md` |
| Rotate the OpenRouter (or any other) API key | `secret-rotation.md` |
| Rebuild after the VM is gone or DuckDB is corrupted | `disaster-recovery.md` |
| Diagnose a specific failure symptom | `debugging.md` |

## When in doubt

Read `debugging.md` first — it indexes failure symptoms to commands and
fixes. If your symptom isn't in the catalogue, the three commands at
the bottom of that runbook ("When in doubt") surface 80% of common
issues.

## Cross-references

- `../SKILL.md` — agent-facing topology overview, where state lives,
  load-bearing architectural constraints. Read this if you're an agent
  picking up the infrastructure cold.
- `../README.md` — operator-facing summary. Prerequisites, first-time
  setup pointer, cost.
- `../../docs/architecture_notes.md` (in the Antiek repo proper, not
  in `infrastructure/`) — substrate-level commitments that the
  infrastructure is shaped around. Read for "why is the deployment
  this specific shape" questions.

## What the runbooks won't tell you

- **Why an architectural choice was made.** That's in
  `../SKILL.md` under "Constraints that look weird," or in
  `../../docs/architecture_notes.md` for substrate-level decisions.
- **How the substrate code works internally.** That's in the Antiek
  code itself; start at `interfaces/research/api/app.py` and
  `orchestration/loop_one/orchestrator.py`.
- **Cost-per-investigation projections.** Run the cold-question demo
  and read the `dispatch.call` events; sum `cost_usd`. Sample numbers:
  a substantive cited-thesis run costs ~$0.15 (mostly Claude Opus
  synthesizer); a hollow `insufficient_evidence` run costs ~$0.08.
