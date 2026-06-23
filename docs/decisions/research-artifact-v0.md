# ResearchArtifact v0 — ratified at implementation (ANT-AHT)

**Date:** 2026-06-23  
**Source spec:** `docs/htmlspec/antiek-html-transport/`  
**Status:** Implemented (Profile B transport)

## Decision

- **Canonical truth:** DuckDB graph + typed event log. HTML is a rendered **agent lens**.
- **Storage:** `~/.antiek/research-artifacts/<investigation_id>.html` (override: `ANTIEK_RESEARCH_ARTIFACTS_DIR`).
- **Machine channel:** `<script type="application/json" id="antiek-artifact-v1">` in the same file as human sections.
- **Telemetry:** `artifact.generated` with `artifact_kind="other"` and `intent="research_artifact_v1:<id>"` until `ArtifactKind` gains a dedicated literal (schema bump).

## Schema v1 fields

`investigation_id`, `problem_question`, `insights[]`, `open_questions[]`, `synthesis_excerpt`, `synthesis_withheld`, `source_event_ids[]`, `content_hash` over canonical JSON.

## Rejected

- HTML-primary editing without events (bypasses single-writer).
- Committing artifacts to git (noisy diffs).

## Reconsider if

- Operator requires two-way HTML import → SPR-AHT-03 import path.
- Dedicated `artifact_kind="research_artifact"` → bump `EVENT_SCHEMA_VERSION`.