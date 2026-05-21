# UI redesign — archive + onboarding

Compact pointer doc for the next developer. The full programme retro
is `RETRO.md` next to this file; the canonical specs are the 14
`sprint_*.html` + `brand_werner.html` pages. This is the one-pager.

## What shipped

A panel-system shell with Werner the penguin as the brand mascot.
Eight + light-variant sprints landed on `main` between the brand
commit and the S12 close-out:

```
brand(ui-redesign) → sprint(0-1-2) → sprint-3 → sprint-4 → sprint-5
→ sprint-6 → sprint-7-light → sprint-8-light → sprint-9
→ sprint-10-light → sprint-11 → sprint-7-full → sprint-8-full
→ sprint-10-full(status) → sprint-12 → spec-compliance follow-ups
```

Operator-visible features: brand-outlined panels (dock left/right/
bottom, float, popout via window.open), persistence per route + per
investigation, URL-shareable `?ws=` layouts, TipTap notebook editor
with 9 block kinds + slash menu + local autosave + conflict detection,
keyboard shortcuts (⌘K/⌘B/⌘/, ⌘[/⌘], G+I/W/N/R), reduced-motion +
viewport-tier responsive, axe-core advisory panel per Storybook story.

## Where things live

| You want to | Open |
|---|---|
| Brand bible | `docs/ui_redesign_posthog/brand_werner.html` |
| Per-sprint spec | `docs/ui_redesign_posthog/sprint_*.html` |
| Programme retro | `docs/ui_redesign_posthog/RETRO.md` |
| Werner assets | `apps/reading/src/brand/` |
| Lemon primitives | `apps/reading/src/components/lemon/` |
| Panel system | `apps/reading/src/workspace/` |
| Shell chrome | `apps/reading/src/AppShell.tsx` + `components/navigation/` |
| Notebook editor | `apps/reading/src/modes/Notebook/Editor.tsx` |
| Tests | `apps/reading/src/**/*.test.{ts,tsx}` (Vitest) |
| Visual regression | `apps/reading/.lostpixel/baseline/` |

## How to add a new panel kind

1. Pick a stable `PanelKind` name (`"FooSurface"`). Edit
   `src/workspace/panel.types.ts` to add it to the union.
2. Build the renderer component at `src/modes/Foo/Surface.tsx`. Receives
   the panel's `props` spread directly.
3. Register the kind in `src/workspace/PanelRegistry.tsx` with a
   `React.lazy(() => import(...))` import.
4. Optionally add a workspace-action helper to `src/workspace/actions.ts`
   (`openFooSurface({...})`) so callers don't repeat the
   `useWorkspace.getState().open(...)` dance.
5. (Optional) Add a starter to a route's `PanelHost` so the panel
   opens automatically with the route.

## How to update Lost-Pixel baselines

A visual change that affects rendered Storybook stories will fail CI
(`.github/workflows/visualtest.yml`, threshold 0.4 %). To accept the
new look as the truth:

```bash
cd apps/reading
npm run visualtest:update
git add .lostpixel/baseline
git commit -m "chore: rebaseline lost-pixel for <reason>"
```

Commit the `.png` diff in the SAME PR as the source change. Don't
mix unrelated baseline updates.

## How to flip the env flag for rollback

The new shell ships under `VITE_ANTIEK_UI=v2` (default). If a serious
regression surfaces in production:

```bash
# Production deploy ENV
VITE_ANTIEK_UI=v1
```

`src/main.tsx` reads the flag and routes between `<App />` (v2,
default) and `<AppLegacy />` (v1, pre-S4 chrome). See
`src/AppLegacy.tsx` for the legacy mount + `.env.example` for the
exact form.

The legacy shell is intended to stay in the tree for one sprint
after the cutover, then be removed (S13). If S13 hasn't happened
yet, the rollback path still works.

## How to check the bundle is under budget

```bash
cd apps/reading
npm run build:check
```

Asserts the main `index.js` chunk ≤ 700 KB gzipped. Current
headroom is ≈ 427 KB.

## Where to ask

The 14-sprint spec is the canonical reference. If a question can't be
answered from the spec + this archive + the source tree, propose an
amendment to the spec first (a new acceptance-criterion bullet),
then build to satisfy it.
