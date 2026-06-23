# Research artifact agent-notes import v0 — ANT-AHT SPR-AHT-03

**Status:** Implemented (`substrate/research_artifact/import_notes.py`)

## Decision

- Import reads only `agent_notes[]` from `#antiek-artifact-v1` JSON.
- New notes emit `artifact.generated` with deduping intent prefix `research_artifact_agent_note_v1:`.
- Re-export carries forward `agent_notes` from on-disk artifact (`build_body`).

## Rejected

- Importing edited findings/gaps into graph without promotion pipeline (HTML-primary bypass).

## Reconsider if

- Operator needs full two-way merge UI → Write surface + graph review queue.