# Decision: baseline substrate/memory + substrate/agent_skills (reachability gate)

**Date:** 2026-08-07 · **Gate:** `tools/lint/reachability_gate_py.py` (hard CI gate on py3.14)

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

## Reconsider-condition fired: `substrate/agent_skills` (2026-09-22)

The second condition is now true. `substrate/agent_skills` is imported by product paths on
three routes: `services/html_projection/widgets/sketch.py` (the `sketch` widget kind renders
through `sketch_svg`), `roles/thought_partner/prompt.py` (the skill catalog is rendered from
`registry.list_skills()` into the thought-partner prompt) and `interfaces/research/api/app.py`
(`GET /deliverables` summarizes its read-only projection through `py_analysis.summarize_rows`).
The gate reported the entry as STALE once the widget import landed, and the
`package:unimported:agent_skills` entry is removed in the same commit as the prompt and route
wiring, so the gate re-asserts reachability for real: with the entry removed on a tree where
the package is still unimported (pristine main, measured before the wiring) the gate exits 1;
after the wiring it exits 0. The `substrate/memory` entry and its condition are unchanged.
