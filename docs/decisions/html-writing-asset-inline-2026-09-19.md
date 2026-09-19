# Decision: Writing/notebook HTML-native inline view

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** html-native-research-view-2026-09-19 (#3183); ArtifactExport View HTML; HPRJ SPR-06 deliverable/notebook export.

## Context

Research synthesis already serves `GET …/artifact.html` with **`inline`**
disposition. Write (`/api/deliverables/…`) and TipTap notebooks only had
`?format=html` as **`attachment`**. The shared `ArtifactExport` "View HTML"
control already linked `…/artifact.html` for all three surfaces — so Write and
Notebook View HTML **404'd**. Dual-structure: DuckDB remains SoT; HTML is a
script-free projection.

## Decision

1. `GET /api/deliverables/{id}/artifact.html` — inline, zero-script, rights via
   `adapt_deliverable` (cite-only non-servable).
2. `GET /api/notebooks/{id}/artifact.html` — same for TipTap notebooks.
3. Keep `?format=html` as **attachment** (download path distinct from view).
4. Header `X-Antiek-Html-Projection: script-free; disposition=inline|attachment`
   for honesty (no invented trust/CPM bits).
5. Wire `ArtifactExport` on WriteHome open-piece (CreationStudio already had it).

## Non-goals

- Flipping OCR/pypdf converter heuristics.
- `production_default_mount` / Synquery / G2 / email / AppLovin CPM.
- Merging TipTap notebooks with AutoNotebook.

## Consequences

HTML-native daily-use grade rises: Write and Notebook View HTML render in-browser
like research, without inventing content or weakening rights.
