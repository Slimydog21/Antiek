# PostHog Feel — elevation contract (FEEL-S1 deliverable)

## Primitives

| Primitive | Definition | Where |
|-----------|------------|-------|
| Opaque chunky card | `bg-ice-0` / `dark:bg-charcoal-2`, `border-edge border-sun`, `rounded-hog`, depth-mapped `shadow-z*` | Floating `PanelLayoutPanel` |
| Glass scene window | `bg-glass` + blur when focused; ad border is the chunky frame | `WorkspaceWindow` |
| Hover-lift | `hover:-translate-x/y-[2px]` + shadow grow on **handles/cards**, not during drag | Panels, Lemon cards |
| Cascade | ≥20px stagger so prior window/panel edge remains visible | Both stores |
| Focus | `focus-visible:ring-sun` (controls); `outline-sun` (panels/windows chrome) | S5 |

## PostHog OSS (honest)

MIT `frontend/src/layout/panel-layout/` provides **fixed** nav + one resizable tree panel, not a floating z-manager. We borrow **feel primitives** (elevation stamp, inset canvas, resize affordance), not their architecture.

## Exemptions

- **ResearchWorkstation** `/inv/:id` dense IDE — opaque, not stacked glass.
- **GlassSurface** scene landings — no opaque scrim.
- **Werner** layer — no card chrome.

## API (FEEL-S1)

```ts
export type ChromeMode = "opaque-chunky" | "glass-scene";
export function shadowForStackDepth(depth: number, mode: ChromeMode): string;
export function cascadeOffset(index: number): { x: number; y: number };
```