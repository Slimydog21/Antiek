# Decision: Lego insight slotting into Surface E Thought Partner

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: master-spec §4.5 Lego-block slotting; `PaletteDragPayload` / `DRAG_MIME`; CK-4 `POST /compose-context`; `docs/decisions/tp-surface-e-real-panel-2026-09-18.md` residual; write Repository drag.

## Context

Surface E TP pane was real (#TP panel) but still lacked the operator's preferred affordance: *"slot some into focus like legos and challenge them."* Write already treats graph insights as draggable Legos; inventing a second drag contract would be theater.

## Decision

1. **InsightLegoShelf** on the TP panel: `GET /blocks/search` + same `PaletteDragPayload` / `DRAG_MIME` as BlockPalette / Write Repository. Click `+` slots without drag (a11y).
2. **Focus tray** drop target on `ThoughtPartnerPanel`: parse via existing `parsePaletteDrag`; chips + remove; cap 12 deduped.
3. On Send: `composeContext({ items: slotted as @insight })` → merge ahead of picker/reading `system_context` → `POST /thought-partner`. §9.0 stays server-derived.

## Non-goals

- Multi-turn TP thread.
- Dragging insights from Deep Research Canvas into Surface E in this PR (same MIME will accept them if opened later).
- Changing the substrate `selected_notes` retrieval path (auto-retrieve remains; slotted insights are explicit focus via system_context).

## Consequences

TP pane finally hosts Lego focus. Composite TP residual from rollup closes. Next: CLI/Herdr or multi-turn polish.
