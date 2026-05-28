# Auto-notebook — PROPOSED resolution, operator sign-off PENDING

**Date:** 2026-05-28
**Branch:** `caffen/lr-spr06`
**Source spec:** `specs/antiek-living-roadmap/sprint-06-auto-notebook-outcomes.html` (SPR-06)
**Status:** ⚠️ **PROPOSED — operator sign-off PENDING.** This is NOT a ratified
feature. It is built to the operator's proposed resolution behind a visible
"proposed (sign-off pending)" banner, kept reversible to minimal.

## The proposed definition (what a "notebook" is)

The operator's PROPOSED resolution of the long-open "what is a notebook" fork:

> The notebook is the **auto-generated, always-current narrative VIEW** of a
> workstation's insight/question graph. Its outline is **derived from the
> graph's themes**, its **sections ARE the insights / open-questions**, and it
> **regenerates as the graph updates** — it is the *document lens* over the
> *block-lens* canvas (the same graph data rendered as a living document). There
> is **one notebook per investigation, always auto** — there is **no manual
> "save to notebook."** It is the **same artifact SPR-09's Write surface will
> consume** (its dynamic outline feeds Write's dynamic outline).

This is the operator's signal — *"these notebooks should just be automatically
generated… not statically"* — turned into a concrete shape. **It is proposed,
not ratified.** The operator previously left this fork undecided and has now
asked to resolve it; the resolution is recorded here and in the roadmap's FLUID
open-questions register, awaiting sign-off.

## What SPR-06 built (and the discipline it kept)

- **A DERIVED, REVERSIBLE view — NOT a new persisted store.** The auto-notebook
  is computed by a PURE function (`apps/reading/src/modes/Notebook/deriveAutoNotebook.ts`)
  from the EXISTING graph:
  - insights + open-questions via `getDistillation(investigationId)` (the same
    data `DistillView.tsx` reads — `GET /research/{id}/distill`);
  - the synthesis via `parseSynthesis(investigation.events)` (the same parser
    `MasterMdViewer.tsx` consumes), rendered by `MasterMdViewer` itself.
  There is **no `auto_notebooks` table, no parallel store, no new write path.**
  The single-writer DuckDB invariant (CLAUDE.md §16) is untouched — this view
  only READS.
- **It re-derives on graph change.** The React wrapper
  (`apps/reading/src/modes/Notebook/AutoNotebook.tsx`) subscribes to the
  investigation's event stream via the SHARED `useInvestigation` hook (the same
  WS plumbing the workstation uses). A new insight/question node or the
  synthesis settling changes the event list → the distillation re-fetch fires →
  `deriveAutoNotebook()` recomputes the outline + sections from the new graph
  state. The document is the block graph re-rendered, never a saved snapshot.
- **A visible "proposed (sign-off pending)" banner** sits at the top of the auto
  view ONLY (the manual TipTap notebook is a separate, unbannered surface). Copy
  is honest §5 voice: *"Proposed — sign-off pending. This notebook is generated
  from your research's graph and regenerates as you work; the design isn't
  ratified yet."*
- **It renders ONLY real graph content (rigor #1).** No fabricated section,
  insight, or question. An investigation with no distillation and no synthesis
  derives an EMPTY notebook → an honest empty state, not invented content.
- **§9.0 no-leak.** The synthesis section is rendered by `MasterMdViewer`, which
  owns the §9.0 servable guard — a withheld source's body is never served (it
  shows "not available to open"). The auto-notebook inherits that guarantee; the
  derivation carries no claim/chunk bodies of its own.
- **M2 — the static "save to notebook" affordance was removed** from
  `MasterMdViewer.tsx` (the research flow). The auto-notebook supersedes it per
  the operator's directive. The manual TipTap Notebook editor (`/notebook/:id`)
  stays reachable as its own surface — only the *save-FROM-research* button is
  gone, and no dead handler remains (that `openNotebook("NotebookEditor", …)`
  call site was the only static save into the research flow).

## Why labeled "proposed" / why kept reversible

Because the definition is the operator's PROPOSED resolution and **not yet
ratified.** Keeping it a derived view (not a hand-authored store) means
withholding sign-off reverts cheaply to the minimal build. It is deliberately a
**cuttable leaf**: it is NOT a hard dependency of SPR-05 (research home) or
SPR-07 (Read), so removing it cannot break them.

## What would ratify it vs revert it

- **Ratify:** the operator signs off on the proposed definition above. Then the
  banner can come down and the auto-notebook becomes the canonical notebook
  model; the FLUID open-questions entry moves to resolved.
- **Revert to minimal:** the operator withholds sign-off or redirects. Then:
  drop the `/notebook/auto/:investigationId` route, delete `AutoNotebook.tsx`
  and `deriveAutoNotebook.ts` (plus the test), and — if the operator restores
  the static "save this exact state" model — revert the SPR-06 M2 removal of the
  save-to-notebook button in `MasterMdViewer.tsx`. Nothing else depends on it.

## Steelman of the rejected static "save to notebook" model (rigor #2)

A static saved notebook doc is a **stable artifact the user controls**: it does
not churn under them as the graph changes, "I saved this exact state" is a real
and reassuring mental model, and a frozen doc is trivially exportable/citable as
a point-in-time record. That is a genuine affordance the auto-view gives up.

**What tipped the choice to auto-generate:** (1) the operator's explicit
directive that notebooks "should just be automatically generated… not
statically"; (2) the one-graph thesis that a notebook is a *lens over* the graph
("derived view, not a copy"), so a frozen snapshot would be a second source of
truth that drifts from the graph; (3) the PROPOSED resolution that the notebook
IS the document lens over the block-lens canvas and the same artifact SPR-09
consumes. **The "this is mine, it won't surprise me" affordance is preserved
honestly** by the auto view being clearly labeled "proposed — sign-off pending"
and non-authoritative until ratified (and the manual TipTap notebook editor
still exists as a separate surface for anyone who wants a hand-authored doc).

## SPR-09 linkage (do NOT build here)

The auto-notebook's dynamic OUTLINE (`AutoNotebook.outline`, produced by
`deriveAutoNotebook`) is the artifact SPR-09's Write surface will later consume
as its outline. SPR-06 produces that outline shape; it does NOT implement Write.
