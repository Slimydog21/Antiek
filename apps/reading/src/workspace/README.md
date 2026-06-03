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

## Full spec

`docs/ui_redesign_posthog/sprint_03_panel_layout.html`
