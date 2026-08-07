# SWARM BRIEF — codex-cc — memory recall + extraction router (agent-memory spec S2b)

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. STACKED on the account-memory substrate lane — `substrate/memory/` +
`migrate_v10` already exist here (read them first). This completes the memory system: recall + router.

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm5/codex-recall`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm5/memory-recall`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. venv: `~/Antiek/platform/.venv/bin/python`,
  run tests from worktree root. ruff + mypy --strict on new code. Tests on a FRESH temp DuckDB.
- Keep changes ADDITIVE to `substrate/memory/`; do NOT modify the shared graph schema/events files
  further (the substrate lane already did that).

## Context already on this branch (do NOT rebuild — build on it)
`substrate/memory/`: `MemoryItem`, `write_memory_item(con, ...)`, `list_memory(con, owner_user_id,
...)`, owner-scoped + invalidate-don't-delete supersession. Read these + the agent-memory spec S2b:
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/agent-facing-memory-anydoc.md`

## The sub-goal
Add the two pieces that make account-memory USABLE by an agent: (A) RECALL relevant memory into a
prompt, and (B) the extraction ROUTER that decides how a new candidate memory fact reconciles with
existing memory.

### Scope (bounded — exactly this)
1. **Recall** — `recall_memory(con, owner_user_id, *, query=None, limit=N) -> list[MemoryItem]`:
   owner-scoped, returns the most relevant/salient current (non-superseded, point-in-time-valid)
   memory items for a prompt. Rank by a simple deterministic salience (recency + optional lexical
   overlap with `query` using stdlib — do NOT add an embedding/vector dep; DuckDB-VSS/turbopuffer
   are out of scope). Plus a `format_memory_for_prompt(items) -> str` that renders them for
   injection (provenance-tagged).
2. **Extraction router** — `route_memory_update(existing: list[MemoryItem], candidate: MemoryItem)
   -> MemoryDecision` implementing mem0's **ADD / UPDATE / SUPERSEDE / NOOP** as a PURE, deterministic
   function: NOOP if candidate duplicates an existing item; SUPERSEDE if it contradicts one (mark old
   invalid + add new); UPDATE if it augments one; ADD if novel. The LLM that EXTRACTS candidates from
   an interaction is the CALLER's job — you build the reconciliation logic only.

### Acceptance (must pass for real — fresh temp DuckDB)
Tests: recall returns only the owner's current items, salience-ordered, excludes superseded; a
contradicting candidate → SUPERSEDE (old invalidated via the substrate's supersession, new added); a
duplicate → NOOP (no write); a novel candidate → ADD; an augmentation → UPDATE. Report exact pass
counts. mypy --strict clean.

### Non-goals
NO LLM extraction of candidates from interactions (S2c, caller's job). NO app/prompt-pipeline wiring
(S2d). NO embedding/vector store. NO shared-schema edits. Just recall + router + tests over the
existing substrate.

## When done
`git add -A && git commit -m "feat(memory): recall + ADD/UPDATE/SUPERSEDE/NOOP extraction router"`,
then write `DONE.md`: files, exact test command + real result, honest gaps.
