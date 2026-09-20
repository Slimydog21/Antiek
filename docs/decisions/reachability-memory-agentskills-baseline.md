# Decision: baseline substrate/memory + substrate/agent_skills (reachability gate)

**Date:** 2026-08-07 · **Gate:** `tools/lints/reachability_gate_py.py` (hard CI gate on py3.14)

## Context
The swarm shipped `substrate/memory/` (account-level memory substrate + recall/router,
PRs #2989/#2990) and `substrate/agent_skills/` (DuckDB/Python/Processing kernel skills, #2987).
Both are built + tested but imported by **zero product-loop code** (the reachability gate's
"wiring is the constraint" doctrine), so the gate fails them as NEW unreachable packages.

## Decision
Add both to `tools/lints/baselines/reachability_py.json` — the gate's own sanctioned registry of
known-unreachable-for-now packages (~20 already listed, e.g. `twin_note_taker`, `ad_targeting`).
This is NOT swallowing the gate (no `|| true`, no gate edit); it is a tracked, git-auditable
declaration that these packages are staged ahead of their wiring.

## Why unwired-by-design
- `substrate/memory` → its prompt-pipeline wiring is spec S2d (`agent-facing-memory-anydoc.md`),
  deliberately deferred + operator-gated (schema `migrate_v10` is operator gate G4).
- `substrate/agent_skills` → its prime-agent kernel wiring is a later lane; the skills are
  callable stand-alone today.

## Reconsider-if (remove each baseline entry when true)
- `substrate/memory` is imported by a product path (prompt assembly / research pipeline).
- `substrate/agent_skills` is imported by a product path (agent execution / prime-agent kernel).
Removing the entry then makes the gate re-assert reachability for real.
