# SPR-03 — Block-canvas lineage: what the graph carries vs. the gap

**Date:** 2026-05-28
**Sprint:** Living Roadmap SPR-03 (block-canvas, M3)
**Status:** recorded — reconstructable granularity limit

## Why this note exists (rigor #1, intellectual honesty)

The block-canvas draws **lineage edges**. The standing trap (the sprint's rigor
card #1) is to draw a plausible-looking edge to "complete the organism" when the
graph does not actually carry the relation. A fabricated edge is a §9 provenance
lie wearing a UI costume. This note records **exactly what lineage data exists**
so the canvas's granularity limit is reconstructable, and so a future sprint that
wants richer lineage knows precisely which relation it must add to the graph
first (rather than inventing one in the UI).

## What lineage data EXISTS today

1. **`DistilledNode.reserved_child_investigation_id`** (api.ts `DistilledNode`).
   An escalated open-question node may reserve a *child investigation* — the
   deeper research it spawned. This is the one **node-anchored** lineage signal:
   it ties a question node (on this canvas) to a child investigation id.
   - It is a question → *child-research* relation, NOT question → another node
     on this canvas. The child investigation's own nodes are a different
     investigation's graph (a different canvas).

2. **Investigation parent/child tree** (`useInvestigationTree.ts`, via
   `InvestigationSummary.parent_investigation_id`). Investigation-LEVEL
   parent/child, surfaced by `listInvestigations`. Also investigation-scoped,
   not node-to-node.

## What does NOT exist (the gap)

- **There is NO node-to-node lineage field** in the graph today: no
  insight→insight, no question→insight, no "this insight was derived from that
  insight" edge among the nodes of a single investigation. The distill surface
  returns flat lists of insights and questions; neither node carries a
  parent-node pointer.

## What the canvas therefore draws

- For a **single investigation's** canvas (the SPR-03 surface), the only honest
  edge is: an **escalated question block → a "spawned a deeper research" child
  marker** (anchored from `reserved_child_investigation_id`). We render this as
  an edge from the question block down to a small leaf marker labelled
  "spawned a deeper research" — an honest edge-to-child, **not** a dangling
  edge to a node that isn't on this canvas, and **not** a fabricated sibling
  edge.
- A question with **no** `reserved_child_investigation_id` produces **no edge**.
  `deriveLineageEdges` (edgeModel.ts) only iterates the fields that exist, so
  fabrication is structurally impossible — there is no code path that invents an
  edge.
- The investigation-tree signal (#2) is wired into `edgeModel.childInvestigationIds`
  for a future consumer (e.g. distinguishing a *reserved* child from a *launched*
  one), but the canvas draws **no** node-to-node edge from it because no such
  relation exists.

## What would reverse / extend this

If a future sprint adds a real **node-level lineage relation** to the graph
(e.g. a `derived_from_node_id` on insights, or a `graph.edge.inserted` event
typing insight→insight provenance), the canvas can draw those edges by
extending `LineageEdge` with a new `toKind` and a second clause in
`deriveLineageEdges` — *only after* the relation lands in the substrate. Until
then, drawing such an edge would be fabrication.

## M4 theme grouping — DEFERRED

M4 (whiteboard-style theme grouping into regions) is the sprint's explicitly
**lowest-priority and cuttable** milestone (sprint page §M4). It is **deferred,
not shipped** — and recorded here as deferred rather than claimed-met, because
shipping a non-functional region render would be a false-met claim (a §9-style
honesty failure in a UI costume).

**Why deferred.** A region can only be populated by a *region-assign gesture*
(a user action that tags one or more blocks with a shared `region_id`). SPR-03
shipped **no such gesture**. Without it, `region_id` is always null — every
block is ungrouped — so a region can never contain a member, and the region
render would draw nothing (or, worse, a hollow box claimed as "grouping").
Rather than ship a render path that can never fire, we cut it cleanly and leave
a documented forward-compatible seam.

**What shipped (the reserved seam).** The pieces a future M4 needs are in place
and inert:

- **Schema fields** `region_id` / `region_label` on `BlockPositionPayload`
  (`substrate/schemas/events.py`) and on `BlockPosition`
  (`canvasLayout.ts`) — reserved, always persisted as `null` today (the persist
  call in `Canvas.tsx` hardcodes `region_id: null, region_label: null`). These
  are a forward-compatible reserved seam; they are intentionally NOT removed.
- **`ThemeRegion.tsx`** — the presentational region component, kept but **NOT
  mounted** by `Canvas.tsx` (the canvas renders blocks + lineage edges only).
  Its header marks it RESERVED. Its unit test (`ThemeRegion.test.tsx`) survives
  as a reserved-seam unit test of a pure component.
- **`regionBounds`** in `canvasLayout.ts` — the pure geometry helper the region
  render will use, kept and unit-tested.

**Precise follow-up (what a future sprint adds).** Add a
multi-select → "group as theme" → label gesture on the canvas that emits a
`block.positioned` event for each selected block carrying a **shared**
`region_id` (and an optional `region_label`). Then re-derive regions in
`Canvas.tsx` by grouping resolved positions by `region_id`, and **mount**
`ThemeRegion` behind the blocks. No schema change is needed — the fields already
exist; only the gesture + the (previously removed) grouping derivation + the
mount are net-new. Until that gesture lands, mounting `ThemeRegion` would render
an empty layer, so it stays unmounted.

## Boundary note (defensibility)

The canvas is a **free 2D coordinate space**, not the reading-physics
in-document `layout-map` (which anchors widgets to text). Edges are hand-rolled
SVG cubic-bezier paths between block centers (`splinePath`); no graph library
(react-flow) is used — see the SPR-03 handoff steelman.

**Honest note on edge curvature.** The bezier control points are written so the
SAME `splinePath` function bows through the vertical midpoint when an edge's two
endpoints differ in x. But the ONLY edge the canvas draws today is a **vertical
drop** from an escalated question block to its child-research marker placed
directly below it — so both endpoints share the parent block's center x, and the
bezier collapses to a straight vertical segment. There is therefore **no active
horizontal edge-separation today**; the bow is a reserved capability for a future
node→node edge whose endpoints differ in x (which requires the node-level lineage
relation described above to land first). We do not claim a separation behavior the
current single-edge set does not exhibit (rigor #1).
