# compounding/

The property that makes the system compound. The Researchmaxx audit
flagged "the system compounds" as a claim, not a verified property.
This directory holds the verification.

## Modules

- **`domain_skills/`** — Pointers and adapters for the four domain
  skills (`quantum`, `defense`, `ai-infrastructure`, `semiconductor`).
  The actual skill files live at `~/.hermes/skills/research/*-knowledge/`
  and migrate from the existing locations; this module provides the
  loading and diffing surface.
- **`extraction/`** — Post-research distillation. After a research
  cycle, extracts the durable insights from the investigation and
  prepares them for Phase 8 merge into the relevant domain skill.
- **`skill_growth/`** — Programmatic skill update on Phase 8 completion.
  Also hosts the system-proposed-codification infrastructure: when a
  process pattern has been re-derived three times, the orchestrator
  proposes a new process skill. Proposals route to human review.
- **`verification/`** — Compounding-growth measurement. Runs file diffs
  against snapshots and surfaces alerts when Phase 8 was logged as
  executed but the skill files didn't grow. Extends to skill-quality
  metrics: for investigations that used a given skill version, what
  was the average constraint-pass rate, the average archive rate, the
  average outcome correlation? If skills compound correctly, newer
  versions produce better outcomes.

## Scope discipline

Content-quality verification is hard and not fully in scope here. This
module guarantees that growth *happened*, not that growth *was good*.
The latter requires evaluation cohorts and held-out outcome data, which
is a separate problem. See architecture_notes §5.
