# Decision: baseline substrate/memory + substrate/agent_skills (reachability gate)

> **SUPERSEDED for `substrate/memory` (2026-09-22, SPR-11 T3).** Both claims this record
> makes about `substrate/memory` are false on `main`, and its own reconsider-if condition
> below has been met. The package is product-loop code: `interfaces/research/api/app.py`
> calls `account_memory_context(request, req.prompt)` inside the `/thought-partner`
> handler and mounts `account_memory_router` (`/account/memory`) into the app — cited as
> `app.py:6178` and `app.py:7162` in the SPR-11 recon, `:6430` and `:7476` at this
> writing; re-derive with `grep -n 'account_memory_context(request\|include_router(account_memory_router)'`
> rather than trusting either number. The package has two further non-test importers:
> `interfaces/research/api/account_memory_routes.py:16` and
> `acquisition/doc_to_html/converter.py:38`. `tools/lints/baselines/reachability_py.json` no
> longer lists `substrate/memory` at all, so the gate already asserts its reachability
> for real. The `substrate/agent_skills` half is NOT superseded: its baseline entry
> (`package:unimported:agent_skills`) is still present and its reconsider-if still stands.
> Two corrections to the "Why unwired-by-design" section, kept in place below with the
> original wording struck: the `migrate_v10` label is wrong (G4 is the Lemon UI operator
> eye-test, closed 2026-05-23 — `docs/decisions/g4-lemon-ui-verdict.md`,
> `docs/operator_gate_actions.md` quick-status row "G4 Lemon UI verdict"), and
> `migrate_v10_account_memory.py` is an unrun manual script with no caller in any deploy
> path, not an operator gate of any number. Nobody is waiting on the operator for it.

**Date:** 2026-08-07 · **Gate:** `tools/lint/reachability_gate_py.py` (hard CI gate on py3.14)

## Context
The swarm shipped `substrate/memory/` (account-level memory substrate + recall/router,
PRs #2989/#2990) and `substrate/agent_skills/` (DuckDB/Python/Processing kernel skills, #2987).
Both are built + tested but imported by zero product-loop code (the reachability gate's
"wiring is the constraint" doctrine), so the gate fails them as NEW unreachable packages.
*(No longer true of `substrate/memory` — see the superseded banner above.)*

## Decision
Add both to `tools/lints/baselines/reachability_py.json` — the gate's own sanctioned registry of
known-unreachable-for-now packages (~20 already listed, e.g. `twin_note_taker`, `ad_targeting`).
This is NOT swallowing the gate (no `|| true`, no gate edit); it is a tracked, git-auditable
declaration that these packages are staged ahead of their wiring.

## Why unwired-by-design
- `substrate/memory` → its prompt-pipeline wiring is spec S2d (`agent-facing-memory-anydoc.md`),
  deliberately deferred + operator-gated ~~(schema `migrate_v10` is operator gate G4)~~.
  **Correction (2026-09-22):** that label was wrong. G4 is the Lemon UI operator visual
  eye-test, closed 2026-05-23 (`docs/decisions/g4-lemon-ui-verdict.md`;
  `docs/operator_gate_actions.md`). No numbered operator gate tracks the account-memory
  migration: `substrate/graph/migrate_v10_account_memory.py` is an explicit, operator-run
  script with no caller in any `.py`, `.yml` or `.sh` (`git grep -rn migrate_v10` finds
  only the module and its test) — an engineering gap, not a gate. The wiring itself has
  since landed; see the banner at the top of this record. (`substrate/graph/schema.py:109`
  still repeats the "operator-gated" wording in a comment; that comment is wrong for the
  same reason.)
- `substrate/agent_skills` → its prime-agent kernel wiring is a later lane; the skills are
  callable stand-alone today.

## Reconsider-if (remove each baseline entry when true)
- `substrate/memory` is imported by a product path (prompt assembly / research pipeline).
  **Met** — see the banner; the baseline entry is gone and this half is superseded.
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
