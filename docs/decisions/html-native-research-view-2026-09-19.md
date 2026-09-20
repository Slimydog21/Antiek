# Decision: HTML-native research outcome view

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: html-first thesis; Profile B ResearchArtifact; synthesis `artifact.html`; rollup HTML-native ~75.

## Context

Daily research outcomes were still primarily React/`MASTER.md` prose. Synthesis
had `GET /api/syntheses/{id}/artifact.html` but forced **download**
(`Content-Disposition: attachment`). Research investigations could **export**
Profile B HTML to disk (agent channel, includes note-taking script) but had no
browser-viewable script-free projection.

## Decision

1. `GET /research/{investigation_id}/artifact.html` — script-free HTML projection
   via `research_projection_doc_model` + `services.html_projection.render` +
   zero-script gate. DuckDB SoT unchanged. Distinct from POST `/artifact/export`.
2. Synthesis `.html` view route serves **`inline`** (browser displays); 
   `?format=html` download keeps **`attachment`**.
3. `ArtifactExport` + ArtifactOutlineShelf gain **View HTML** (opens `.html`
   in a new tab).

## Non-goals

- Stripping scripts from the editable agent-channel export file.
- Full PDF→HTML converter coverage expansion (separate gap).
- Flipping every surface to HTML-only.

## Consequences

Research outcomes are readable as HTML-native artifacts in the browser.
Composite HTML-native grade climbs with daily-use evidence.
