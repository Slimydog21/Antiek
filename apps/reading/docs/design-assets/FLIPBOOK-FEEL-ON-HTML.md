# Flipbook *feel* on HTML (Antiek path)

Reference demos: [flipbook.page](https://flipbook.page) (Zain Shah / pure generative
stream). Antiek adopts the **product feeling**, not the sole-UI architecture.

## What Flipbook does (observed product intent)

- Illustrations reshape with the window (no rigid layout engine for the art).
- Any region can become interactive — not only pre-authored buttons.
- Video stream at interactive framerate over WebSocket → GPU (Modal-class).

## What Antiek ships instead (cost-intelligent, agent-controllable)

| Flipbook idea | Antiek HTML path |
|---|---|
| Reshape with window | Viewport-normalized scenery hotspots (`interactiveRegions`) |
| Any region interactive | Edge scenery only (center chrome wins; no click-steal) |
| Living imagery | Procedural scene + optional Krea art layers; mascot living TV |
| Pure pixel sole UI | **NO-GO** as exclusive shell — HTML remains agent-native truth |

## Product map (scenery clicks)

See `sceneHotspotProductRoutes.ts` and `BRANDING-LIVING-TV.md`.

## Infra note

Modal + Krea remain available for enrichment. Default path is HTML + tests +
axe/LostPixel gates. Pure generative sole UI stays behind a future NO-GO
revisit with cost ceilings operator-approved.
