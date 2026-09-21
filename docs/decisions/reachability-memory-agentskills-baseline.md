# Decision: baseline substrate/memory + substrate/agent_skills (reachability gate)

> **SUPERSEDED IN PART — 2026-09-21.** The `substrate/memory` half of this decision is false on
> current `main` (verified at `9cd7692ab`, re-verified unchanged at `7922b2b26`). Read this banner
> before the body below it; the body is kept as the 2026-08-07 record, not as a description of
> today.
>
> **`substrate/memory` is wired into the product loop.** Call sites read from `9cd7692ab`:
> `interfaces/research/api/app.py:89` imports `account_memory_context`; `app.py:6373` calls it on
> the thought-partner path and folds the result into the assembled system prompt;
> `app.py:7357-7358` imports and mounts `account_memory_router`. The package has two further
> non-test importers: `interfaces/research/api/account_memory_routes.py:16` and
> `acquisition/doc_to_html/converter.py:38`. (An earlier correction cited `app.py:6178` and
> `app.py:7162`; those line numbers have already moved. Re-derive rather than trust either set:
> `git grep -n 'account_memory' interfaces/research/api/app.py`.)
>
> **`substrate/memory` is no longer baselined.** `tools/lints/baselines/reachability_py.json`
> (`generated_at` 2026-09-20T10:29:17Z) holds 37 violations and none of them mentions `memory`. The
> "Reconsider-if" condition for `substrate/memory` below has therefore already been met.
>
> **The `substrate/agent_skills` half is still accurate.** It is still entry
> `package:unimported:agent_skills` in that same baseline file, and still has zero importers outside
> `substrate/agent_skills/` and `tests/`. Do not read this banner as retiring the whole decision.
>
> **`migrate_v10` is not an operator gate, and it is not G4.** See the corrected bullet under
> "Why unwired-by-design" below.

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
  deliberately deferred.
  **[CORRECTED 2026-09-21]** This line originally read "deliberately deferred + operator-gated
  (schema `migrate_v10` is operator gate G4)". That label is wrong twice over. G4 is the Lemon UI
  operator visual eye-test, closed 2026-05-23 — `docs/operator_gate_actions.md:19` and `:152`, whose
  closure record is `docs/decisions/g4-lemon-ui-verdict.md`. There is no numbered operator gate
  tracking the account-memory schema migration. `substrate/graph/migrate_v10_account_memory.py` is
  an unrun manual script with no caller: its own docstring says "The migration is explicit/
  operator-run: importing or initializing the graph does not execute it against an existing
  database", and `git grep -n migrate_v10 -- '*.py' '*.yml' '*.sh'` finds only the module itself and
  its two test files. No operator is waiting on it. It is an engineering gap, not a gate.
  (`substrate/graph/schema.py:109` still repeats the "operator-gated" wording in a comment; that
  comment is wrong for the same reason.)
- `substrate/agent_skills` → its prime-agent kernel wiring is a later lane; the skills are
  callable stand-alone today. *(Still true as of 2026-09-21.)*

## Reconsider-if (remove each baseline entry when true)
- `substrate/memory` is imported by a product path (prompt assembly / research pipeline).
  **MET — 2026-09-21.** See the banner: three product call sites, and no `memory` entry remains in
  the baseline file.
- `substrate/agent_skills` is imported by a product path (agent execution / prime-agent kernel).
  **NOT met as of 2026-09-21** — the baseline entry is still there and still earns its place.
Removing the entry then makes the gate re-assert reachability for real.
