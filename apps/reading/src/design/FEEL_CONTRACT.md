# PostHog Feel — elevation contract

## Primitives

| Primitive | Definition | Consumer |
|-----------|------------|----------|
| Opaque chunky card | `bg-ice-0` / `dark:bg-charcoal-2`, `border-edge border-sun`, depth-mapped `shadow-z*` | Floating `PanelLayoutPanel` |
| Glass scene window | `bg-glass` + blur when focused; **title-bar** depth shadow only | `WorkspaceWindow` |
| Hover-lift | `motion.ts` `press` / `cardLift` on handles and cards | FEEL-S2/S4 |
| Cascade | ≥20px stagger; prior edge visible | Both stores via `cascadeOffset()` |
| Focus ring | outline on panel/window chrome | FEEL-S5 |

## Layer diagram

Canonical source: `zIndex.ts` (`Z_LADDER_ORDER`, pinned by `zIndex.test.ts`).
Read top-to-bottom = top-of-stack to bottom-of-stack.

```
z=200  toast            LemonToast — nothing occludes a toast
z=150  adOverlay        AdBorder full-bleed overlay (pointer-events-none)
z=120  popover          SlashMenu / command popovers — above an open modal
z=100  modal            LemonModal scrim + dialog
z=60   mascot           floating mascot — above panels/windows, below modals
─────────────────────────────────────────
LAYER B  WorkspaceStore — opaque when floating
         z=2…50  PanelLayoutPanel (floatingPanelBase=2 → floatingPanelCeiling=50;
                 the store's zCounter walks up on focus)
         z=5     sceneBadge — SceneStatusBadge over the scene floor
         z=0–1   docked (flat); raised=1 lifts a docked panel over dock chrome
─────────────────────────────────────────
LAYER A  windowsStore — glass over scene
         z≥40   WorkspaceWindow (windowBase=40; interleaves the floating
                band but always under the modal/popover/toast stack)
─────────────────────────────────────────
z≈0     the living scene (mountainscape) + BrainPresence ambience
```

### Known off-ladder call sites (documented, owned by the overlay pass)

The ladder is a catalogue + drift tripwire; these call sites currently sit
off it and are being fixed separately (work-queue Q8) — do not "fix" them by
editing the diagram:

- `BrainPresence.tsx` — inline `zIndex: 1`, uncatalogued; gets a named
  `scenePresence` rung in the same pass.

Fixed by the Q8 overlay pass (2026-09-21): `FloatMenu.tsx` now consumes
`zIndex.popover` (120); `ChunkModal.tsx`, `ProductsLauncher.tsx` and the
LinkMonster detail modal are rebuilt on LemonModal (the `modal` rung, z=100,
with Esc, scrim dismissal and the focus trap).

## Motion — the ambience slot (adjudication D9)

The 80/150/800 ms token scale governs *interaction feedback*; its 800 ms
`slow` value is the longest sanctioned interaction flourish. Scene ambience
is a separate category and lives in its own — fifth — motion slot:
`motion/sceneMotion.ts`'s 1200 ms painted-art crossfade
(`CROSSFADE.durationMs`) and the 31–67 s ambient drift loops (`DRIFT`) are
**ambience, not interaction**, and are exempt from the 800 ms ceiling.
Bounds on the slot: ambience must be non-blocking, must never gate or
accompany a user action's feedback, must stay behind content (z≈0), and must
collapse to a static frame under `prefers-reduced-motion`. Everything that
*is* interaction feedback obeys the token ceiling; the interaction slots are
enumerated in `motion/README.md`.

## PostHog OSS (honest)

MIT `frontend/src/layout/panel-layout/` is a **fixed** shell (left nav + resizable tree + right `SidePanel`), not a floating z-stack OS. This programme ships **interaction physics** (elevation stamp, cascade, hover-lift) without PostHog product copy or nav IA.

## Exemptions

Listed in `elevation.ts` as `ELEVATION_EXEMPT_SURFACES`: ResearchWorkstation dense IDE, GlassSurface landings, the mascot illustration layer (still named "Werner illustration layer" in `elevation.ts` pending the batch rename pass).

## API

```ts
import { cascadeOffset, shadowForStackDepth, type ChromeMode } from "./elevation";
```

See `elevation.ts` and `elevation.test.ts` for tier assertions.