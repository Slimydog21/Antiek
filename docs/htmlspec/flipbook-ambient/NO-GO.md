# Flipbook full generative stream — NO-GO (session branding/UI goal)

**Date:** 2026-07-12  
**Decision:** Continuous full-screen generative video (Flipbook `flipbook.page` pure-pixel mode: model-streamed UI, no HTML layout engine) is **out of the pass bar** for Antiek's reading shell.

## Evidence already in tree

- AMS-v2 stream spike: Krea / Flux path measured ≈ **7 s TTFG**, ≈ **0.136 gen fps** — far below any interactive 24 fps / 1080p stream.
- Budget math in `apps/reading/src/scene/useSceneArt.ts`: ~$0.60/min would exhaust a 50-unit cap in ~3.3 min.
- Shipped path is **HTML/CSS/JS** with:
  - Procedural floor always-on (`useSceneClock` → Peaks / Clouds / Snow)
  - Mood-gated optional Krea art crossfade (budget / kill-switch / no-key → fallback)
  - Viewport-adaptive interactive regions (`scene/interactiveRegions.ts`) for Flipbook *feel* without abandoning the layout engine

## What we did ship (Flipbook *feel* on HTML)

1. Adaptive ambient mountainscape that resizes with the viewport.
2. Interactive hotspot map (hover/click regions over scene layers).
3. Cost-intelligent generative tint only when keys + budget allow — never required for a correct shell.
4. Living Werner mascot (cursor bait / product reactions / games) as the character layer.

## Revisit conditions

A future GO requires measured sub-second generative frames (or a true LTX-class stream on Modal/Krea) under a hard cost cap, plus a deliberate product decision to dual-path pure-pixel vs HTML. Until then, pure-pixel Flipbook remains inspiration only.
