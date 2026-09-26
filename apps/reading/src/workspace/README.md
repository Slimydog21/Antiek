# `src/workspace/` — panel layout substrate (the 3D layered window manager)

The heart of the redesign: a workspace shell where the operator opens, stacks,
drags, resizes, pins, and pops out independent **panels** — each panel being
one of the existing Antiek modes or a sub-surface (investigation list,
trajectory viewer, notebook, AI sidecar, chase flow, claim inspector, etc.).

S0 leaves this directory empty. S3 lands the system:

- `WorkspaceStore.ts`     Zustand store: `panels[]`, `zOrder`, `focusedPanelId`,
                          `dockLeftIds`, `dockRightIds`, `floatingIds`, `pinned`,
                          `schemaVersion`
- `PanelLayout.tsx`       orchestrator — reads store, lays out dock zones +
                          floating layer + main slot
- `PanelLayoutPanel.tsx`  individual panel renderer (4 modes: docked-left,
                          docked-right, floating, popout)
- `PanelHost.tsx`         opt-in wrapper a Route component renders to live
                          inside the panel shell
- `PanelHandle.tsx`       drag / resize / kebab-actions strip on every panel
- `PanelRegistry.tsx`     map from `PanelKind` to a React.lazy renderer
- `panel.types.ts`        `PanelDescriptor`, `PanelMode`, `WorkspaceSnapshot`
- `panelLayoutLogic.ts`   pure helpers (z-reorder, dock-snap, persistence)

## Rules

1. Panel descriptors are pure data. Rendering lives in `PanelLayoutPanel`.
2. State changes go through `WorkspaceStore` actions; no direct mutation.
3. URL + localStorage persistence is bolted on in **S9**; S3 builds the
   in-memory store only.
4. New panel kinds added later means **one entry** in `PanelRegistry` +
   one type added to `PanelKind` — no orchestrator changes.

## Z-index conventions

| Layer                    | z-index |
|--------------------------|---------|
| Dock chrome              | 0       |
| Docked panels            | 1       |
| Floating panels          | 2–50    |
| `LemonModal`             | 100     |
| `LemonToast`             | 200     |

## Chrome mode (PostHog Feel)

| Store | Renderer | Mode | Elevation |
|-------|----------|------|-----------|
| `WorkspaceStore` | `PanelLayoutPanel` (floating) | **opaque-chunky** | `shadowForStackDepth(depth, "opaque-chunky")` — wired FEEL-S2 |
| `WorkspaceStore` | docked panels | flat | depth 0 — no stack shadow |
| `windowsStore` | `WorkspaceWindow` | **glass-scene** | minimal title-bar shadow — wired FEEL-S3 |

Contract: `src/design/FEEL_CONTRACT.md` + `elevation.ts`. ResearchWorkstation IDE is **exempt** (dense opaque center, not a floating stack).

## Cockpit chrome (C2/C3, 2026-09-24)

`PanelLayout` has two layout presets, held on the store outside
`WorkspaceSnapshot` (`panel.types.ts` `CockpitChrome`):

- `docked` (default) — the docks as above, DOM unchanged.
- `omarchy-inset` — the same slot structure inside an inset frame: an outer
  gap where the scene background shows, two tall rounded rectangles
  (`radius.lg`, `border-hairline`) — primary material (left dock + main
  slot) left, companion (right dock) right. Presentation only: `dockSide()`
  collapse behavior, the `{mainSlot}` contract, and the tier-`sm` early
  return are unchanged, and an empty right dock still collapses.

The preset persists via its own global blob
(`persistence.ts` `antiek.workspace.layout-preset`, the custom-hotkeys
precedent — never folded into the per-scope layout snapshot). Pane keys are
keymap rows like every other key: prefix h/l (+ `ctrl+alt` twins) move pane
focus with a ring (`ring-focus`; in `docked` they cycle dock areas via
`cycleFocus`); prefix f fullscreens the focused pane (Esc — element-scoped
on the layout root, never a global binding — or the same key restores);
prefix i toggles the preset.

## The companion (C4, 2026-09-24)

The right inset pane IS the companion: AI agents as tabs
(`CompanionPane.tsx`, one component, two mounts — the inset right pane's
content; the docked preset's "Companion" right-dock panel). State lives in
`companionStore.ts` (stable per-agent ids, close as a view act, activation
order, wrap cycling); tab kinds come from `companionRegistry.tsx` as DATA —
islands and diligence slot in later as new entries. Shipped kinds:
research-thread (the shared `researchState` vocabulary over
`useInvestigationList`) and dialogue (the one-shot
`components/ai/thoughtPartnerOnce.ts` wire — never a chat). Keys: prefix
n/p (+ `ctrl+alt+]/[` twins) cycle agent tabs, only while the pane is
visible. The cross-pane seam is `crossPane.ts`: `openDocumentInLeftPane`'s
EVENT SHAPE is the contract; since PR 3 (D6) the handler spawns a left child
tab in the current mothership's tab tree — callers never change.

## Document tab tree (D6, 2026-09-24)

The left pane's document space is an infinitely nested tab tree over the
pure model (`tabTree.ts`, MS-04 — TAB ≠ BRANCH: navigation state, never
provenance). One tree per mothership (research/writing/reading), driven by
`tabTreeStore.ts` and rendered by `DocumentTabStrip.tsx` (mounted once in
PanelLayout's shared centre column — inset left pane and docked main area
share it; router-guarded). The strip shows the active path (hier numbers are
the addressing), the Opus `Trail` as the ancestry breadcrumb (fed by
`documentSpace.threadForPath` in Trail's lawful one-entity form), a tree
panel with subtree focus (prefix `t`), and an undo affordance after closes.
Keys: prefix `n`/`p` siblings (the corpus's canonical tab keys — companion
cycling moved to prefix `,`/`.`), `u` parent, `o` last-visited child, `c`
close-with-lift, `shift+x` prune, all with `ctrl+alt` twins where one was
lawfully reserved. Persistence is ONLY through a `TabTreeAdapter` (§1.6:
never web storage) — the in-memory adapter makes trees session-scoped until
lane B's HTTP adapter lands (`setTabTreeAdapter` is the seam).

## Write mode (C5, 2026-09-24)

In writing mode the right pane switches from the companion to the outline
(`RightPaneForMode.tsx` — one component contract on the route's mothership;
the docked preset surfaces it as the "WriteOutline" right-dock panel,
auto-opened on piece routes). `WriteOutlinePane.tsx` renders one tab per
outline block, each a drop target for source documents (repository hits and
reader tabs carry `application/x-antiek-source-document` payloads).
Assignments land in `blockSources.ts` — the honest session-scoped bridge
(write_routes has no block-source mutation today; the
`setBlockSourcesBackend` seam is the write-through contract, never a
pretend-write). The left tree holds the full body as tab 1 with one child
tab per section (`writeTreeSync.ts`); WriteHome scopes its view to the
active tab. Agents stay on the AI sidecar (mod+/), untouched; prefix ,/.
cycles whichever right pane is on screen.

## Full spec

`docs/ui_redesign_posthog/sprint_03_panel_layout.html`
