# S10 status — bulk migration

The S10 spec splits into two distinct slices. This doc tracks both.

## Slice 1 — visual-token sweep (DONE)

Every src/modes/*.tsx file under main is on the brand palette. The
S10-light commit (`c5f1e5a`) + its fixup (`a31035a`) processed:

- 35 mode files swept
- ~1100 stone-* / amber / emerald / red references replaced with
  ink / ice / sun / aurora / emperor tokens + dark: variants
- 0 stone-* references remain anywhere in `src/`

Day mode + dark mode now work across every route.

## Slice 2 — structural `PanelHost` wraps per route

Reality check: every route already renders inside `AppShell`'s
`PanelLayout` via the route Outlet (the S4 wire-up handles that). A
route component renders directly into the main slot. Per-route
`PanelHost` wraps with starter panels are an OPT-IN — they only make
sense for routes that have natural side surfaces.

### Wrapped (with starter panels)

| Route | File | Starters |
|------|------|---------|
| `/` + `/inv/:id` | `modes/ResearchWorkstation/index.tsx` | `InvestigationSidebar` docked-left + `Chat` docked-bottom (when an investigation is loaded) |
| `/wrestle/:id` | `modes/WrestleApp/index.tsx` | `Notes` docked-left + `CrossDocs` docked-right |

These were ported in S5 + S6.

### Not wrapped (intentional — no clear side surfaces)

These routes render their content directly in the main slot. The
brand chrome (NavRail + Topbar + PanelLayout) wraps everything;
nothing breaks. If a future feature wants to add starter panels
to one of these, the wrap is a 3-line change inside the route's
`index.tsx` (see `ResearchWorkstation/index.tsx` for the template).

| Route | Why no wrap |
|------|-------------|
| `/sources` | Single LemonTable; no side surfaces |
| `/notebooks` | Single LemonTable index |
| `/documents` | Single LemonTable index |
| `/investigations` | Single LemonTable index |
| `/billing` | Plan card + invoice table; no side surfaces |
| `/stats` | Dashboard cards |
| `/map` | Single SVG viewport |
| `/backtest/:id` | Detail view |
| `/privacy` | Compliance cards |
| `/pricing` | Plan cards |
| `/operator` | Operator dashboard cards |
| `/outcomes` + `/outcomes/:id` | Index + detail |
| `/payouts` | Audit table |
| `/trust` | Public compliance cards |
| `/skill-rules` + `/skill-rules/:id` | Index + detail |
| `/federation` | Graph viewer |
| `/cross-graph/citations` | Citation list |
| `/loop-3` | KPI dashboard |
| `/interview/:id` | Recording + transcript (could benefit from PanelHost in a future pass; not blocking S10) |
| `/interviews` | Index |
| `/replay/:id` | Linear playback (could benefit from a step-list docked-left in a future pass) |
| `/create/:id?` | Lego-block creation (could benefit from a block-palette docked-left in a future pass) |
| `/brainstorm` | Parked questions surface (could benefit from a `Chase` floating-panel CTA in a future pass) |

The "could benefit" routes are flagged as opt-in opportunities for
whoever owns them. None of them are blocking the redesign's
operator-visible exit criteria.

### What the S10 spec table called out vs reality

The S10 spec (`docs/ui_redesign_posthog/sprint_10_migration.html`)
enumerated 28 routes. Of those:

- **2 already wrapped** (S5 + S6): RW + Wrestle
- **26 visually swept** (S10-light): cards/buttons/inputs match brand
- **0 structural failures**: every route renders correctly inside AppShell
- **5 "could-benefit" candidates** noted above for opt-in future work

The redesign's exit criterion — "every route lives inside the new
chrome" — holds. Routes that need their own panel layout get it
when they need it; the workspace primitives + `openNotebook` /
`openPdfPanel` / `openClaimInspector` helpers (from
`src/workspace/actions.ts`) make those wraps simple to add.

## What this commit doesn't do

- Add starter panels to the 5 "could-benefit" routes above. That's
  per-route product judgement, not a blanket mechanical pass.
- Migrate hand-rolled tables → `LemonTable`. Visual tokens are
  swapped; structural primitive swaps are per-route polish.
- Add per-route stories beyond what already exists.

Spec: `docs/ui_redesign_posthog/sprint_10_migration.html`
