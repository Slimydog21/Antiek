# Flipbook full generative stream — no-go

**Date:** 2026-07-12  
**Corrected:** 2026-07-15  
**Decision:** Continuous full-screen generative video—Flipbook's pure-pixel
model-streamed UI without an HTML layout engine—is outside Antiek's current
pass bar.

## Evidence

- The AMS-v2 Krea/Flux spike measured approximately 7 seconds to first
  generation and 0.136 generated frames per second, far below an interactive
  1080p/24fps stream.
- The measured cost path at roughly $0.60/minute would exhaust a 50-unit cap in
  approximately 3.3 minutes.
- Antiek's shipped authority remains semantic HTML/CSS/JS. Optional generated
  atmosphere may decorate that substrate but may not own navigation, content,
  accessibility, or correctness.

## Correction to the former record

The former no-go record claimed `scene/interactiveRegions.ts` and a generalized
interactive hotspot map had shipped. Repository history, branches, worktrees,
and current source contain neither. That statement was false.

SPR-39 introduces one bounded Home-only composition: four semantic HTML
workflow buttons positioned over decorative authored geography. The same
ordered list becomes a mobile itinerary and remains usable when the image is
unavailable. This is not a reusable pixel-hotspot engine, a canvas UI, runtime
generation, or evidence of production deployment.

## What is allowed now

1. Adaptive authored atmosphere that resizes with the viewport.
2. Home-only spatial composition whose routes, labels, focus order, and hit
   targets are owned by semantic HTML.
3. Optional cost-capped generative tint that is never required for a correct
   shell.
4. Werner mascot reactions and games as a separate character layer.

## Revisit conditions

A future go requires measured sub-second frames or a true LTX-class stream on
Modal/Krea under a hard cost cap, plus a deliberate product decision and an
accessible HTML fallback. Until then, Flipbook is interaction and atmosphere
inspiration, not Antiek's rendering authority.
