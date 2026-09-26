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

- `docked` (default) — the docks as above.
- `omarchy-inset` — the same slot structure inside an inset frame: an outer
  gap where the scene background shows, two tall rounded rectangles
  (`radius.lg`, `border-hairline`, named regions "Primary pane" and
  "Companion pane") — primary material (left dock + main slot) left,
  companion (right dock beneath it) right. The companion pane is on screen
  at every tier from md up: at md it narrows to 280 px instead of vanishing,
  and the lg dock-collapse rule is the docked preset's alone.

Both presets and every fullscreen state render ONE element tree (sweep v2
F-17): the inset's pane shells are `display: contents` wrappers in the
docked preset, and fullscreen HIDES a pane or dock (`hidden` attribute plus
the `hidden` utility) instead of unmounting it, so a preset toggle or a
fullscreen round trip never remounts the route, a draft or a docked panel.
Fullscreen is never invisible state (F-18): a chip ("Fullscreen · Esc")
restores it by pointer, the docked preset's prefix f with no dock open is a
no-op, and a panel opened into a side fullscreen hides restores the layout
(`WorkspaceStore.hiddenByFullscreen`).

The preset persists via its own global blob
(`persistence.ts` `antiek.workspace.layout-preset`, the custom-hotkeys
precedent — never folded into the per-scope layout snapshot). Pane keys are
keymap rows like every other key: prefix h/l (+ `ctrl+alt` twins) move pane
focus with a ring (`ring-focus`; in `docked` they cycle dock areas via
`cycleFocus`); prefix f fullscreens the focused pane (Esc from any focus —
a document listener that exists only while a pane is fullscreen, never a
keymap row; Esc in a text field or a dialog stays theirs — or the same key
restores; right-pane fullscreen fills the cockpit);
prefix shift+i toggles the preset (no chord; `i` is the attention inbox's).

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
n/p (+ `ctrl+alt+]/[` twins) cycle agent tabs while the right pane has
focus (see "Keys" below), only while the pane is visible. The cross-pane seam is `crossPane.ts`: `openDocumentInLeftPane`'s
EVENT SHAPE is the contract; since PR 3 (D6) the handler spawns a left child
tab in the current mothership's tab tree — callers never change.

## Document tab tree (D6, 2026-09-24)

The left pane's document space is an infinitely nested tab tree over the
pure model (`tabTree.ts`, MS-04 — TAB ≠ BRANCH: navigation state, never
provenance). One tree per mothership (research/writing/reading), driven by
`tabTreeStore.ts` and rendered by `DocumentTabStrip.tsx` (mounted once in
PanelLayout's shared centre column — inset left pane and docked main area
share it; router-guarded).

Stage 2 of the cockpit rescue (2026-09-26) rebuilt the strip to DESIGN-MODEL
§2a:
- **Path header** (`TabPathHeader.tsx`): root → active tab, every crumb a
  link; past four crumbs it compresses to `1 › … › parent › current`, the
  ellipsis opens the whole path and Esc closes it.
- **Sibling strip** (`SiblingStrip.tsx`): the active tab and its siblings as
  an ARIA tablist (manual activation, one roving tab stop, ←/→/Home/End)
  controlling the route content (`documentPanel.ts`, marked `tabpanel` while
  the strip is mounted), with a `↳ n` chip for the active tab's children.
- **Tree panel** (`TabTreePanel.tsx`, prefix `t`): an ARIA tree over
  `tabRows.flattenTabRows` (depth-first pre-order), indent capped at six
  levels with a `dN` badge past it, virtualised fixed-height rows, subtree
  focus with "up".
- **Labels** (`tabLabels.ts` over `tabTitles.ts`): titles derived from the
  ref (a book's title, a research question, a piece or section heading),
  resolved lazily or registered by the surface that holds them; a raw id is
  never a label. Long numbers compact to `1…4.2` beside a label.
- **Route adoption** (`documentSpace.adoptTabForRoute`, applied by
  `routeSync.ts`): a route change adopts an open tab that shows it before
  seeding a root, so a child stays a child. Its activations are "route"
  activations and never navigate.
- **Activation navigates, nothing else does** (sweep v2 F-04): a USER
  activation (strip, keys, close/undo, the cross-pane seam) leaves a
  `navIntent` stamped with the history entry it was issued at; the strip
  takes it once and navigates only if the route does not already show the
  tab and the operator has not navigated since. No effect infers navigation
  from whichever tab is active, so a mode switch, a reload or a load never
  hijacks the navigation that brought the operator here. The cross-pane seam
  adopts the route before choosing a parent (an agent open that beats the
  lazy strip still lands as a child), and an open that resolves after the
  operator navigated opens without taking the screen. A tab whose route belongs to another mode carries `?m=<tree>` so it
  never switches trees (`mothershipForPath(pathname, search)`). A Write
  section tab activates to its own piece (`routeTabFor`).
- **Branches from a document** (`branchNavigation.ts`, `useBranchTo.ts`,
  repair round 1): a deep research spun from the reader, a document opened
  from it and a Write citation traced to its source navigate with a branch
  intent in the history state; the route sync files the new surface as a
  CHILD of the tab it came from, in that tab's tree.
- **Close** is held locally for 10 s behind a `toast.undo` (LemonToast's undo
  slot, `UNDO_TTL_MS`); the close joins the snapshot only when the window
  lapses, and a save queued before the close waits too (the hold is checked
  when a save runs; a 409 inside the window keeps the close held). In the
  tree panel, Delete prunes a row and Shift+Delete closes only that tab
  (§2a's two outcomes). Loading/error/empty use the shared state primitives, and a failed
  tree load offers "Try again" (`retryLoad`).

Keys (the lane-A cockpit decision, stage 3, recorded in
`docs/decisions/mothership-keys-herdr-prefix.md`): prefix `n`/`p` and
`ctrl+alt+]`/`[` cycle the FOCUSED pane's tabs — the document siblings on
the left, the agent tabs (block tabs when writing) on the right, the left
when neither pane is focused (`shortcuts.ts` `tabKeySide`). `u` parent, `o`
last-visited child, `t` the tree panel, each with a `ctrl+alt` twin.
`shift+x` closes the tab and its branches (§2a's default), prefix only.
`c` / `ctrl+alt+c` (new tab) and `i` / `ctrl+alt+i` (attention inbox) are
held for surfaces not yet built: their handlers return "not mine" and the
key sheet marks them "Not built yet" (`keymapView.ts` `PENDING`).
Persistence is ONLY through a `TabTreeAdapter` (§1.6: never web storage) —
the in-memory adapter makes trees session-scoped until lane B's HTTP adapter
lands (`setTabTreeAdapter` is the seam).

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
active tab. Agents stay on the AI sidecar (mod+/), untouched; with the
right pane focused, prefix n/p cycles its block tabs. A section tab scopes
the piece in place, so the strip names it by its heading and never says
"opens as window". A drop that is not a source document is refused in words
(`parseSourceDragPayload`) and assigns nothing.

## Full spec

`docs/ui_redesign_posthog/sprint_03_panel_layout.html`
