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
EVENT SHAPE is the contract; the PR-2 handler bridges to the reader window,
PR 3 swaps the handler, callers never change.

## Full spec

`docs/ui_redesign_posthog/sprint_03_panel_layout.html`
