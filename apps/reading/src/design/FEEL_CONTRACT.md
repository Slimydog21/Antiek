# PostHog Feel — elevation contract

## Primitives

| Primitive | Definition | Consumer |
|-----------|------------|----------|
| Opaque chunky card | `bg-ice-0` / `dark:bg-charcoal-2`, `border-edge border-sun`, depth-mapped `shadow-z*` | Floating `PanelLayoutPanel` |
| Glass scene window | `bg-glass` + blur when focused; glass border frame | `WorkspaceWindow` |
| Hover-lift | `motion.ts` `press` / `cardLift` on handles and cards | FEEL-S2/S4 |
| Cascade | ≥20px stagger; prior edge visible | Both stores via `cascadeOffset()` |
| Focus ring | outline on panel/window chrome | FEEL-S5 |

## Layer diagram

```
z=200  LemonToast
z=100  LemonModal
─────────────────────────────────────────
LAYER B  WorkspaceStore — opaque when floating
         z=2…50   PanelLayoutPanel
         z=0–1    docked (flat)
─────────────────────────────────────────
LAYER A  windowsStore — glass over scene
         z≥40   WorkspaceWindow (WINDOW_Z_BASE=40)
```

## PostHog OSS (honest)

MIT `frontend/src/layout/panel-layout/` is a **fixed** shell (left nav + resizable tree + right `SidePanel`), not a floating z-stack OS. This programme ships **interaction physics** (elevation stamp, cascade, hover-lift) without PostHog product copy or nav IA.

## Exemptions

Listed in `elevation.ts` as `ELEVATION_EXEMPT_SURFACES`: ResearchWorkstation dense IDE, GlassSurface landings, Werner layer.

## API

```ts
import { cascadeOffset, shadowForStackDepth, type ChromeMode } from "./elevation";
```

See `elevation.ts` and `elevation.test.ts` for tier assertions.