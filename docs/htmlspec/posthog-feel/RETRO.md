# PostHog Feel — retrospective

**Sprints:** FEEL-S1–S6 (2026-06-03 caffenagent run)

## Shipped

- Single elevation contract (`src/design/elevation.ts`) for opaque panels + glass title bars
- Floating panels: depth-mapped shadows, handle `press`, cascade via `cascadeOffset`
- Glass windows: title-bar-only depth shadow, cascade aligned to contract, AMS title-bar separation assert
- RW: example prompt `cardLift`, dense IDE exempt guards
- Focus: `feel-focus.css`, panel `outline-sun`, static + e2e focus gates
- `npm run e2e:feel`, matrix spec, this verification doc

## Held

- Did not merge `windowsStore` into `WorkspaceStore` (AMS ownership)
- Did not opaque-convert glass window bodies
- Did not claim PostHog product clone

## Follow-ups (non-blocking)

- Wire `windowsStore` / `panelLayoutLogic` to import cascade constants (drift guard)
- Promote `feel-panels-cascade` into `e2e:ams` once Storybook boots in that project
- Chase floating panel inherits S2 automatically via `PanelLayoutPanel` — no extra work needed