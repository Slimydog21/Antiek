# skills/domain/

Accumulated facts and frameworks per topic area. Updated via Phase 8
after each research cycle.

## Current domains

- `quantum-knowledge/`
- `defense-knowledge/`
- `ai-infrastructure-knowledge/`
- `semiconductor-knowledge/`

The actual skill files live at `~/.hermes/skills/research/*-knowledge/`
on the deployed system and migrate from the existing Researchmaxx
locations. This directory holds in-repo references and the schema
each skill file must conform to.

## Verification

`compounding/verification/` diffs each skill against the prior snapshot
on every Phase 8 transition. Non-growth fires an alert; growth without
quality is captured by the per-skill-version backtest metrics
(architecture_notes §3.2 and §6).
