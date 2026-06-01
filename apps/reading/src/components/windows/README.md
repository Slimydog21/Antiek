# Workspace windows (SPR-09)

Transparent, ad-bordered, draggable/expandable **workspace windows** that host
whole product pages over the SPR-04 mountainscape — multipliable like a
developer's terminals. Built on the real floating primitives (no new
window-manager dependency, D6).

## Files

| File | Role |
|---|---|
| `../../workspace/windowsStore.ts` | Multi-window state (a NEW slice, disjoint from `WorkspaceStore`). |
| `WorkspaceWindow.tsx` | The window frame: title bar, drag, resize, expand↔restore, close, focus/z-order, glass body, keyboard a11y, reduced-motion, perf degradation. |
| `WindowAdBorder.tsx` | The Times-Square ad frame (four edges) reusing the Read-mode `AdBorder` + `AdFillView`. House fallback (never blank) + suppression + `onImpression`. |
| `windowHostContext.ts` | `useInWindow()` — the window-adaptation contract seam. |
| `openWindow.ts` | Spawn API + the `WINDOW_PAGES` registry + the windows-vs-navigate policy + `windowKindForRoute`. |
| `WindowsLayer.tsx` | Renders every open window over the scene. Mount once in the shell. |

## Integration (one line — AppShell stays untouched)

SPR-09 must NOT edit `AppShell.tsx` (SPR-04 owns it). `WindowsLayer` is
self-contained: drop it into the working region's relative container as a
sibling over the route Outlet —

```tsx
<WindowsLayer />
```

It reads `windowsStore` + `WINDOW_PAGES`; no props. The orchestrator / SPR-04
owner wires that single line.

## Window store schema (`windowsStore.ts`)

```ts
WorkspaceWindowDescriptor = {
  id: string;            // stable; one per kind by default (re-open focuses)
  kind: string;          // route-ish key → WINDOW_PAGES renderer
  mode: "floating" | "full";
  rect: { x, y, width, height };  // floating geometry; preserved across expand→restore
  z: number;             // within the windows layer (WINDOW_Z_BASE + z = rendered z-index)
  title: string;
  payload: Record<string, unknown>;  // handed to the hosted page (e.g. { documentId })
}

WindowsSnapshot = { windows, order /* bottom→top */, focusedId, zCounter }
```

- **Independent windows.** Each has its own rect/mode/z; focusing one restacks
  only that window.
- **Focus restacks z + order.** Newest-focused is topmost; on close, focus
  falls back to the next-topmost (or null when none remain).
- **Bounded fan-out.** `MAX_WINDOWS = 8` (hard cap). At the cap, `open()`
  focuses the oldest window instead of exceeding the cap and returns *its* id
  (a real id, never a phantom) — surfaced honestly, never silently dropped. 8
  mirrors a realistic terminal fan-out and keeps 8 transparent frames + the
  animated scene inside the SPR-11 FPS budget. Now that a default click opens a
  window (see the inversion below), this cap is the hot-path backstop: a rapid
  run of default activations can never exceed 8. Kept at 8 deliberately — do
  not change the value or the at-cap action shape without recording a reason
  here and in `windowsStore.ts`.
- **Z base.** `WINDOW_Z_BASE = 40` — a window always sits over the scene (z≈0)
  but under the in-page modal/toast stack (LemonModal z=100).

## Windows-vs-navigate policy — INVERTED in AMS2-SPR-04

> **The inversion (record it here; the next reader looks here and in
> `openWindow.ts`).** In SPR-09 a window was the *additive* affordance and
> full-page navigation was the default for everything — windows were manual,
> buried behind a `⊞` button, so the operator never actually saw one (v1
> complaint #2). AMS2-SPR-04 **inverts that for within-contract surfaces**: a
> default click on a within-contract, reference-like page now opens a **window**
> over the scene. Windows are the default *interaction*, not an extra.

The inversion is **scoped, not total** — the steelman of full-page navigation
still wins where it wins (simpler, zero adaptation, one focused task), so it
stays the default exactly there:

- **Window is the default** for **within-contract** surfaces — the pages that
  satisfy the two-line window-adaptation contract (drop opaque bg + fill
  container) and own no internal dock: `Stats`, `Library`, and the product
  **sub-action** surfaces launched from `ProductsLauncher`. A default click on
  these floats a window; no buried button required.
- **Navigate full-page stays the default** for:
  - **Primary workflow switches** (Research ↔ Read ↔ Write ↔ Speak via the
    NavRail) — these are destinations, not companions.
  - **Out-of-contract surfaces** that own their own dock/floating panel system
    or assume the full viewport: the **ResearchWorkstation IDE** and the
    **WrestleApp PDF wrestler**. Nesting a dock-owning page inside a window is
    out-of-contract; they are **reported, not redesigned** — we never bolt on a
    third adaptation to force them to float. (Owner boundary: SPR-05 owns the
    scene/NavRail; these pages own their own viewport.)

`ProductsLauncher` no longer hides windows behind `⊞`: a product/sub-action
click opens a window by default for the contract-verified, window-eligible
kinds. The eligible set is `WINDOW_PAGES` in `openWindow.ts` (the
inversion's machine-readable boundary).

> **The sub-action window is a launcher-into-a-page, not a persistent
> companion.** Activating a product floats a `subaction` window listing that
> workflow's destinations; clicking a destination ROW navigates full-page and
> CLOSES the sub-action window (`SubActionList.tsx` `onRow`). So the FIRST
> click floats a window and the SECOND click (the chosen destination) leaves
> it — by design. The window is the menu, not the destination; the destination
> page is what the operator settles into (and may itself be out-of-contract,
> e.g. the ResearchWorkstation IDE). A reader expecting the destination itself
> to keep floating alongside the menu is expecting the wrong thing.

## Persistence — in-memory, session-scoped (deliberate)

`windowsStore` has **no `persist` middleware**. Window state lives only in
memory for the life of the tab:

- A **reload starts with zero windows** (the store re-initializes to `EMPTY`).
- This is a **choice, not an oversight.** Workspace windows are an ephemeral
  arrangement of the operator's *current* task ("multiple terminals laid out
  right now"), not a saved document. Persisting stale floating geometry +
  payloads across reloads would resurrect windows pointing at since-changed
  routes/assets — more surprising than helpful.
- **Named future-persistence path** (if later desired): wrap `useWindows` with
  zustand's `persist` middleware keyed on the restorable subset of each
  descriptor — `{ kind, payload, rect, mode }` — and rehydrate by *replaying*
  `open()` so `MAX_WINDOWS` and the monotonic z-restack invariants still hold
  (do **not** rehydrate `z` / `order` / `zCounter` verbatim). This is a deferred
  task, not a silent assumption.

## Window-adaptation contract (M4)

The ONLY edits permitted to a hosted page: **(a)** drop its opaque full-bleed
background so the glass + scene shows through, and **(b)** fill its container
(`h-full`) instead of forcing the viewport height (`h-screen`). Both are gated
on `useInWindow()`, so the full-page route is byte-for-byte unchanged at
runtime. A page needing MORE than (a)+(b) is **out-of-contract** → reported, not
redesigned.

### Pages adapted (exact surgical diffs)

Both pages carry the identical two-line diff:

`src/modes/Stats/index.tsx` and `src/modes/Library/index.tsx`:

```diff
+ const inWindow = useInWindow();
  ...
- <div className="flex flex-col h-screen">
-   <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
+ <div className={`flex flex-col ${inWindow ? "h-full" : "h-screen"}`}>
+   <main className={`flex-1 overflow-y-auto ${inWindow ? "bg-transparent" : "bg-ice-0 dark:bg-charcoal-2"}`}>
```

`DocumentsIndex` shares the same structure and is a future drop-in (not wired
yet — kept to the verified two pages this sprint).

## Ad border (M3)

Reuses the Read-mode `AdBorder` (`AdFillView`, `kind:"ad"|"house"`). Fills are
**supplied by the parent** (never fetched here). No buyer → the `kind:"house"`
fallback renders a useful recommendation, **never blank**. A suppressed edge
degrades any paid ad to house and reports via `onSuppressed`; `onImpression`
fires once per served paid-ad edge. Static creatives → reduced-motion safe by
construction.

## Performance (M7) + degradation strategy

- The **focused** floating window pays for live glass (`backdrop-blur-glass`);
  **unfocused** windows drop the blur (the cheapest big win) and dim to 95%.
- A **full** ("expanded") window goes opaque (`bg-glass-solid`), so the shell
  can pause the scene blur entirely behind it (nothing of the scene shows).
- `MAX_WINDOWS = 8` bounds the worst case.

**FPS:** a precise FPS number could not be honestly measured in the headless
jsdom test environment (no compositor / rAF frame timing). The degradation
strategy is encoded in code and asserted in tests (unfocused → no blur). A real
on-device FPS sweep with N windows + the live scene is left for SPR-11's
measurement harness.

## Popout (M6) — DEFERRED (justified)

The existing popout (`workspace/popout.ts`, route `/_panel/:panelId`,
BroadcastChannel) renders a **panel** via `PanelRegistry`. Workspace windows
host **pages** via a different registry (`WINDOW_PAGES`) and a different
rendering contract (glass body, ad border, window-adaptation). Reusing popout
for windows needs a parallel `/_panel`-equivalent route that maps window kinds
— and that route lives in `App.tsx`, which is risky to edit mid-merge.

Deferred rather than half-built. **Reuse path when picked up:** add a
`/_window/:windowId` route rendering a page from `WINDOW_PAGES` (mirroring
`PanelWindowApp`), and add a "pop out" window action that calls a
`openWindowPopout(id)` modeled on `openPopoutFor`. The window descriptor's
`{ kind, payload }` is already serializable for the BroadcastChannel handoff.
