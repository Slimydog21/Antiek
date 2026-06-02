# docs/

Design rationale and architectural notes that should outlive any
individual implementation.

- **`architecture_notes.md`** — The big one. Preserves the
  Researchmaxx audit findings, the Agent-paradigm-shift principles,
  the non-negotiable substrate decisions, the preserved strengths of
  the prior codebase, and the validation criteria for the eventual
  hardware decision. Read this before making any architectural change.

- **`docs/agent-execution/HARD_TO_VARY.md`** — ANT-H2V hard-to-vary protocol
  for agent sessions (with `TEMPLATES.md`). Read before diagnosing or
  closing Research/cascade bugs. Program index:
  [`docs/htmlspec/antiek-hard-to-vary-execution/index.html`](htmlspec/antiek-hard-to-vary-execution/index.html).

Additional docs land here as the build proceeds:

- `migration_log.md` (planned) — what moved from where, when, why.
- `schema_versions.md` (planned) — schema-version changes and their
  migration paths.
- `decision_log.md` (planned) — short notes on choices made along
  the way (e.g., "we chose write-lock over Redis queue because…").
