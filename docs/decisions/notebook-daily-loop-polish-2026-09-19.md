# Decision: Notebook daily-loop polish (empty / write handoff / discoverability)

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: AutoNotebook (SPR-06 ratified), DistillView `OpenAutoNotebookLink`, prompt-telemetry panel, Write `ConnectResearch`, vision map pillar 2.

## Context

AutoNotebook was signed off as a derived narrative view. Distill already linked “Open notebook →”. Gaps vs daily-use 100: empty state lacked loop CTAs (filled had only back-to-research); no Write handoff from the notebook; command palette listed TipTap notebooks but not auto-notebook for the open investigation; empty telemetry was loud beside an empty notebook.

## Decision

1. Shared `NotebookLoopNav`: back to research · distill · Write (`/write?investigation=`) · notebooks index — empty and filled AutoNotebook.
2. WriteHome honors `?investigation=` to pre-select that project in ConnectResearch (existing create path; no new API).
3. Command palette: when on `/inv/:id`, offer “Auto-notebook for this research”.
4. DistillView link copy: “Open auto-notebook →” (discoverability).
5. Prompt telemetry: quieter empty copy + `data-telemetry-empty` when `call_count===0`.

## Non-goals

- Auto-importing outline into Write sections (SPR-09 still owns that).
- New DuckDB notebook store.
- Merging TipTap NotebooksIndex with AutoNotebook.

## Consequences

Daily loop discoverability improves without inventing surfaces. Next: TP SERVABLE mount or composite 100.
