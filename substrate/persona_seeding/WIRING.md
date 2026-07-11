# Persona seeding adoption seam

This package is pure and owns no readers, stores, graph clients, model calls, or dispatch.

The research-loop owner should adopt it at the existing decomposition boundary: read an asset's serialized twin records, retain only `kind == "question"`, read the asset's serialized graph-neighborhood records, and pass both snapshots to `grounding_facts` and `derive_personas`. Then call `generate_questions` with the run's canonical `TierBudget`, followed by `build_sub_run_descriptors`. The gathering runner should dispatch each descriptor as a separate context and expose only its `persona`, `questions`, `corpus_refs`, and budget slice.

At the process boundary, receivers must parse the complete sibling payload bundle with `parse_sub_run_descriptors(parent_budget=..., grounding_facts=...)`. The bundle parser rejects unknown fields, unresolved grounding, cross-parent or duplicate identities, non-dispatchable slices, and aggregate slices above the parent tuple. Parsing one descriptor is available for narrow tooling, but it does not replace the bundle-level aggregate check or the runtime budget ledger's spend authority.

Adapters must map twin records to `note_id`, `asset_id`, `kind`, `text`, and graph neighbors to `node_id` plus `canonical_label` (or `text`). They must not weaken validation or substitute unresolved IDs. An LLM-backed question generator may be injected into `generate_questions`; exceptions and malformed output intentionally stop descriptor creation.

Do not route this through a new general decomposer. The existing `roles/decomposer` and cascade planner remain authoritative for flat/tree decomposition; their owners may explicitly select this persona-conditioned seam where doctrine W5 applies.
