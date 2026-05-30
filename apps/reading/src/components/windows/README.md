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
  focuses the oldest window instead of exceeding the cap — surfaced honestly,
  never silently dropped. 8 mirrors a realistic terminal fan-out and keeps 8
  transparent frames + the animated scene inside the SPR-11 FPS budget.
- **Z base.** `WINDOW_Z_BASE = 40` — a window always sits over the scene (z≈0)
  but under the in-page modal/toast stack (LemonModal z=100).

## Windows-vs-navigate policy (M5)

Full-page **navigation stays the default** (simpler, zero adaptation, matches a
single focused task). A **window** is justified only for the operator's
"alongside, not instead" / multiple-terminals case.

- **Open a window** when the operator explicitly wants a floating/secondary
  view, or the surface is reference-like and benefits from coexisting with the
  page that spawned it (Library shelf, Stats, a document, an outcome).
- **Navigate full-page** for primary workflow switches (Research ↔ Read ↔
  Write ↔ Speak via the NavRail), for surfaces that own their own
  dock/floating panel system or assume the full viewport (the
  ResearchWorkstation IDE, the PDF wrestler — **out-of-contract** for windows),
  and for deep/operator context-switches from the launcher.

`ProductsLauncher` keeps `navigate()` for its rows and gains an additive `⊞`
"open in window" button only for window-eligible (contract-verified) modes.

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
