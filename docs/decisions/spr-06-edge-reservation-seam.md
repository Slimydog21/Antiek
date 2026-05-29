# SPR-06 edge-reservation seam — the contract with SPR-07's ad border

**Date:** 2026-05-29
**Branch:** `caffenB/SPR-06`
**Sprint:** SPR-06 — app-shell restructure (bottom nav, igloo home, autonomous Werner waddler)
**Status:** landed; the seam ships at ZERO inset (no visible border this sprint).

## Why

The product is moving to an always-on Times-Square ad border that wraps the
window on all four edges. For that border to be SYMMETRIC, the working region
must consume the full screen width — which the old left NavRail prevented (it
ate the left edge and made the layout left-asymmetric). SPR-06 moves the nav
to a horizontal BOTTOM rail and frees all four edges. SPR-07 mounts the actual
border. This doc is the contract between the two: the single place SPR-07
reads to know where to paint and how the shell reserves space for it.

## The seam

Four CSS custom properties, declared in `apps/reading/src/design/tokens.css`
(`:root`), DEFAULT `0px`:

    --akb-border-inset-top
    --akb-border-inset-right
    --akb-border-inset-bottom
    --akb-border-inset-left

`AppShell` (`apps/reading/src/AppShell.tsx`) is the SINGLE consumer. Its outer
frame (`[data-akb-shell-frame]`) fills the viewport (`h-screen w-screen`) and
applies the four vars as `padding-{top,right,bottom,left}` with
`box-sizing: border-box`. Everything else — Topbar, the full-width working
region, the bottom NavRail, PanelLayout's docks — renders INSIDE that padded
frame. The roaming PenguinMascot is mounted OUTSIDE the frame on purpose (a
free agent over the whole window, not chrome bounded by the inset).

At the default `0px` the padding is a no-op: SPR-06 changes no pixels.

## What SPR-07 does (the fill)

1. Set the four `--akb-border-inset-*` vars to the border thickness (one
   shared value for a symmetric border; the four are kept separate so an
   asymmetric border remains possible without touching AppShell).
2. Paint the reserved padding band — the strip between the viewport edge and
   the padded frame — as the ad border. The four edges are already free and
   symmetric, so the border is symmetric by construction.

SPR-07 should NOT re-introduce a left gutter, move the nav off the bottom, or
add a second inset source of truth. If SPR-07 needs more than a uniform inset
(e.g. a thicker bottom for a banner), it sets the relevant var — the seam
already supports per-edge values.

## Rejected alternatives

- **A dedicated `<BorderSlot>` layout component instead of CSS vars.** Heavier
  and premature: SPR-07 hasn't decided whether the border is one element or
  four edge strips. CSS vars + a padded frame reserve the space without
  committing to the border's internal structure, and any border implementation
  can read the same vars.
- **Insetting at the NavRail / Topbar level individually.** That would scatter
  the inset across several components and let them drift. One frame, one set
  of vars, one consumer.
- **Shipping a visible 1px border now "to prove the seam".** Out of scope and
  would change pixels SPR-06 has no mandate to change. The seam is proven by
  the vars existing + AppShell consuming them at zero, not by painting.
