# Flipbook pure-pixel sole UI — NO-GO (2026-07-16)

## Verdict

**NO-GO** for continuous generative video / pure-pixel stream as the *sole*
Antiek UI surface in this branding wave.

## Why (hard to vary)

1. **HTML vision is load-bearing.** Coding agents control Antiek via HTML/CSS/TS.
   A sole model-streamed pixel surface removes the agent-native control plane.
2. **Cost & latency.** Flipbook-class 1080p@24fps WebSocket GPU (Modal/LTX-class)
   is not budgeted as default interactive chrome. Prior Krea TTFG measurements
   (when available in fleet history) did not clear interactive bars for full-shell
   continuous stream.
3. **Accessibility & testability.** axe-core, LostPixel, Vitest hit-tests, and
   keyboard focus require a real DOM. Pure pixel streams fail the ship bar.

## What we ship instead (Flipbook *feel*)

Documented in `docs/design-assets/FLIPBOOK-FEEL-ON-HTML.md`:

- Viewport-adaptive scenery hotspots (`interactiveRegions`)
- Edge-only hit targets (primary chrome wins)
- Living Werner TV (reaction bus + session brand)
- Procedural scene floor + optional Krea art enrichment under caps

## Revisit triggers

- Operator-approved cost ceiling for Modal GPU stream
- Measured interactive TTFG/fps with axe+LP still green on dual-path (HTML chrome
  + optional ambient stream layer, not sole UI)
- Explicit product decision to dual-render (not replace) HTML

## Evidence

- Branding densify wave PR #2416 tip `0c7354e56` (axe+LP green)
- `docs/design-assets/BRANDING-DENSIFY-SUMMARY.md`
