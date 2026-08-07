# SWARM BRIEF — codex-cc — account-level memory substrate (agent-memory spec S2a)

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. Executes the SUBSTRATE of the long-term account-level memory (the headline new ask).

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm4/codex-memory`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm4/account-memory`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. venv: `~/Antiek/platform/.venv/bin/python`,
  run tests from worktree root. ruff + mypy --strict on new code.
- Do NOT run the migration against any real/prod DB — tests use a FRESH temp DuckDB only.

## The sub-goal
Build the durable, per-account memory SUBSTRATE that persists across all interactions AND
documents, riding the EXISTING DuckDB knowledge graph (no competing store). Read this spec IN FULL
first (sections 5 + 8, esp. the S2/migration items):
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/agent-facing-memory-anydoc.md`
Also read: `substrate/graph/migrate_v9_insight_question.py` (the migration pattern + the `edges`
CREATE TABLE), `substrate/graph/ops.py` (insert_document, owner_user_id), and the
`antiek-thought-partner-memory` spec under `~/Antiek/specs/` for the memory model to generalize.

### Scope (bounded — exactly this; SUBSTRATE only, no recall/router yet)
1. `substrate/graph/migrate_v10_account_memory.py` — a migration that (a) adds a `'memory'`
   `node_type` to the nodes CHECK constraint (DuckDB can't ALTER a CHECK → rebuild the table via
   the staging-copy pattern migrate_v9 uses), and (b) adds `owner_user_id TEXT` to the `edges`
   table (verified missing — only nodes carry it). Idempotent + reversible-safe like migrate_v9.
2. `substrate/memory/` (new) — a `MemoryItem` model + `write_memory_item(con, *, owner_user_id,
   subject, predicate, object, provenance, valid_from)` that inserts a `memory` node + an
   owner-scoped edge, and `list_memory(con, owner_user_id, ...)`. Adopt Graphiti's
   **invalidate-don't-delete** (a superseded item gets `valid_to` set, never hard-deleted).
   Single-writer-safe (goes through the existing serialized writer / con).

### Acceptance (must pass for real — fresh temp DuckDB)
Tests: migrate_v10 on a fresh DB adds the memory node_type + edges.owner_user_id (assert schema);
running it twice is idempotent; write_memory_item inserts a memory node + owner-scoped edge;
superseding an item sets valid_to and keeps the old row (invalidate-don't-delete); list_memory is
owner-scoped (user A never sees user B's memory). Report exact pass counts. mypy --strict clean.

### Non-goals (later lanes — do NOT build)
NO recall-into-prompts / retrieval ranking (S2b). NO extraction router (ADD/UPDATE/SUPERSEDE/NOOP
from interactions — S2c). NO wiring into the live app or auto-running the migration in prod (that
is operator gate G4). NO turbopuffer / competing vector store. Just the migration + memory
write/list substrate + tests.

## When done
`git add -A && git commit -m "feat(memory): account-memory substrate + migrate_v10 (schema+write)"`,
then write `DONE.md`: files, exact test command + real result, honest gaps (incl. G4 deploy gate).
