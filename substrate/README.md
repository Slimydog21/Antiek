# substrate/

The shared core that both surface applications (research, interview)
depend on. Substrate code is provider-agnostic and source-agnostic; it
does not know whether content came from an arXiv paper or a captured
interview, and it does not know which LLM provider answered the last
dispatch call.

## Modules

- **`event_log/`** — Typed, append-only event log. The source of truth.
  Graph state is derived by replaying events. Every action that
  mutates state — every ingest, every extraction, every retrieval,
  every synthesis attempt, every skill update — is captured here.
- **`graph/`** — DuckDB-backed knowledge graph. Schema, ingest, extract,
  search, traverse. Derived from the event log; never mutated directly.
- **`dispatch/`** — Multi-model LLM router with provider abstraction.
  Routes by role, latency requirement, and cost. Configured in
  `config.yaml`; routing changes never require code changes.
- **`schemas/`** — Pydantic schemas for events, nodes, edges, syntheses.
  These are the eventual training-data format. Schema discipline is
  load-bearing; underspecified schemas now produce bad training data later.
- **`attribution/`** — Source-to-output citation tracking. Handles both
  public sources (papers, books, articles) and primary-interview
  sources (with consent, contribution, and citation-rights metadata).
- **`context_pack/`** — Per-role context assembly with hierarchical
  memory. Assembles the bundle the dispatch router actually sees:
  recent session context, relevant long-term skill content, retrieved
  graph evidence, phase metadata, parameter version stamp. Context
  packs are themselves typed events.
- **`constants.py`** — One file, one set of parameters, versioned.
  `ANTIEK_PARAM_VERSION` is stamped into every archived synthesis.

## Non-negotiables (from the spec)

- The event log is append-only and the source of truth.
- The dispatch router accepts a `context_pack`, not just a prompt.
- Schemas are versioned. Bumping schema version is a deliberate act.
- Every parameter that influences a model decision lives in
  `constants.py`, not scattered across role implementations.

See `docs/architecture_notes.md` §2 for the reasoning.
