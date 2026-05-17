# roles/

Inherited from Researchmaxx with consolidation and upgrades. The
prior codebase had two role implementations (`roles.py` and
`role_orchestrator.py` + `role_prompts.py`) that may have diverged;
the migration consolidates to one canonical implementation here.

Each role is a single function (or small class) that takes a
`context_pack` plus role-specific arguments and emits typed events.
Roles consume `substrate/constants.py` and the role-tier mapping in
`substrate/dispatch/config.yaml`.

## Roles

- **`decomposer/`** — Top-level question → sub-questions. Pro-tier
  model; reasoning depth matters.
- **`evidence_retriever/`** — Per sub-Q evidence retrieval against the
  graph. Flash-tier; volume dominates.
- **`parameter_extractor/`** — Structured parameter extraction from
  retrieved evidence. Flash-tier; schema-constrained output.
- **`connector/`** — Cross-domain connection via graph traversal.
  Critically, the LLM is constrained to propose connections only
  among candidates already surfaced by embedding search — this
  prevents hallucinated cross-domain links. Pro-tier.
- **`synthesizer/`** — Tier-aware synthesis with hedging. Highest
  quality tier (Claude or equivalent); cost is dominated by value here.
- **`user_agent/`** — Synthetic user for multi-turn evaluation.
  Load-bearing for interview-workflow development — lets us iterate
  without burning real subject time. See architecture_notes §3.4.

## Discipline

There is exactly one canonical implementation of each role here. Role
prompts and tier choices live in config, not in scattered Python
strings. Role outputs are typed events; the role does not write to
DuckDB directly.
