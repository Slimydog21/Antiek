# Storybook discipline · Antiek reading app

Storybook is the **design-system source of truth** for the Antiek reading UI.
Every component lives next to its story. Visual regression runs against every
story via Lost-Pixel. This document is the short contributor contract for
keeping that working.

## Running

```bash
npm run storybook            # dev server on :6006
npm run build-storybook      # static build → storybook-static/
npm run visualtest           # build + run Lost-Pixel against baseline
npm run visualtest:update    # build + capture a new baseline (intentional)
```

## When to add a story

| You touched…                                | Add or update a story?                       |
|---------------------------------------------|-----------------------------------------------|
| A new component in `src/components/`        | **Yes — required, paired `*.stories.tsx`**    |
| A new Lemon primitive in `src/components/lemon/` | **Yes — required**                       |
| A new panel in `src/workspace/` (S3+)       | **Yes — at least a default-state story**      |
| A new mode subcomponent in `src/modes/`     | Yes when it has a meaningful isolated render  |
| A new route in `src/modes/<Mode>/index.tsx` | No (routes are tested in the live app)        |
| Existing component, visual change           | **Update baseline**: `npm run visualtest:update` then commit `.lostpixel/baseline/` |
| Existing component, behavioural change      | Add a new variant story for the new state     |

## Story conventions

```tsx
import type { Meta, StoryObj } from "@storybook/react";

import MyComponent from "./MyComponent";

const meta = {
  title: "Lemon / MyComponent",     //  Lemon / · Loop 1 / · Legacy / · Design /
  component: MyComponent,
  parameters: { layout: "padded" }, // or "fullscreen" for full-shell scenes
  tags: ["autodocs"],
} satisfies Meta<typeof MyComponent>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { /* props */ } };
```

**Titles** are namespaced. The current namespaces:

- `Lemon / *` — primitives from `src/components/lemon/`
- `Loop 1 / *` — reading-workstation subcomponents
- `Loop 2 / *` — wrestling-workstation subcomponents
- `Loop 5 / *` — interview subcomponents
- `Legacy / *` — pre-redesign chrome that hasn't been retired yet
- `Design / *` — moodboard + showcase + token surfaces

## Fixtures

Mock data for stories that don't talk to the live API lives at
`src/components/__fixtures__/`. Use these exports rather than reaching into
hooks or the network. Schema changes in `generated/types.ts` surface here
immediately via strict-TS.

```ts
import { mockInvestigationCompleted, mockEventStream } from "@/components/__fixtures__";
```

## Hook-coupled components

Some components consume hooks that fetch from the live substrate
(`useInvestigationList`, `useInvestigationTree`, etc.). In Storybook
isolation they render their empty state when no backend is running.

**Known coverage gap**: `InvestigationSidebar` has hook-only data
sources. A future pass adds MSW (mock-service-worker) so stories drive
the hook responses; tracked as a S11 follow-up.

If you write a hook-coupled story today, document the limitation in
the story comment and ship the empty-state render.

## Visual regression (Lost-Pixel)

Every story is screenshotted at build time. Lost-Pixel diffs against
the committed baselines in `.lostpixel/baseline/`.

- **Advisory** in S2 — diffs print to console but don't fail CI yet.
- **Blocking** in S12 — `visualtest` runs on every PR that touches
  `apps/reading/` and a failure blocks merge.

Baseline workflow:

```bash
# you made an intentional visual change
npm run visualtest:update         # screenshots updated
git add .lostpixel/baseline       # commit alongside the source change
git commit -m "ui: tighten LemonButton hover (visualtest baseline updated)"
```

If a diff surprises you, **don't** update the baseline blindly. Open
`.lostpixel/diff/<story>.png` first and look — visual regressions hide
in there.

## Preview background ramps

The Storybook toolbar exposes background presets matching the brand
surface ramp:

- `ice-0`, `ice-1`, `ice-2` (default), `ice-3` — day surfaces
- `ink` — high-contrast headers and chrome
- `space-2 (night)`, `charcoal-2 (night card)` — preview night-mode rendering

Toggle your OS appearance to Dark to see the full night-mode rendering
because the `dark:` Tailwind variants follow `prefers-color-scheme`.

## Brand reference

- `docs/ui_redesign_posthog/brand_werner.html` — the Werner brand bible
  (mascot, palette, highlighter, animation principles).
- `docs/ui_redesign_posthog/sprint_02_storybook.html` — this sprint's spec.
- `src/design/tokens.ts` — canonical TS tokens used by all components.

## What we explicitly skip

- Story for `modes/<Mode>/index.tsx` route entry points — routes are
  tested in the live app, not in isolation.
- Stories that exercise routing — `MemoryRouter` is wrapped at the
  preview level, but per-story navigation behaviour is a live-app concern.
- Stories that capture mic / camera / WebSocket — `InterviewVoiceCapture`
  ships a visual-only story; capture behaviour needs the live app.
