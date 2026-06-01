# Antiek Mountain Shell v2 — Verified Interfaces (the anti-fiction ledger)

> **What this file is.** The single source of truth every AMS-v2 sprint (SPR-02…SPR-10)
> cites instead of its imagination. Every row was checked with
> `git cat-file -e origin/main:<path>` on **2026-05-31**. A row is `VERIFIED`
> only if that command exits 0 on the exact path printed; a row is `NEW-to-build`
> if the path is absent on `origin/main` and someone must build it.
>
> **Why this file exists.** AMS-v1 shipped against fictional interfaces
> (`#scene-root`, `FloatingSurface`, `SubActionLauncher`) that never resolved,
> and was never reconciled. This ledger + the ref-lint (`tools/specs/verify_spec_refs.ts`)
> make that class of error mechanically impossible: a sprint page citing a bare
> (non-`NEW:`) path that is absent fails the lint at spec-review time.
>
> **How to re-check a VERIFIED row.** Run, from the repo root:
>
> ```sh
> git cat-file -e origin/main:apps/reading/src/scene/Scene.tsx && echo PRESENT
> ```
>
> Exit 0 ⇒ the row is still true. Re-run the ref-lint over any sprint page:
>
> ```sh
> tsx tools/specs/verify_spec_refs.ts specs/antiek-mountain-shell-v2/sprint-0X-*.html
> ```

**Baseline commit:** `origin/main` @ `ebfb36a` ("Merge pull request #34 … caffen/arxiv-ingest"), checked 2026-05-31.

---

## Legend

| Verdict | Meaning |
|---|---|
| `VERIFIED` | `git cat-file -e origin/main:<path>` exits 0. The path + the shape below are real on `origin/main`. |
| `NEW-to-build` | The path is **absent** on `origin/main`. A named sprint must create it. Cite it only with a `NEW:` prefix in sprint pages, or the ref-lint fails. |

---

## 1. Shell + scene (the visibility surface)

| Concern | Path | Verdict | Key exports / shape | Notes for downstream sprints |
|---|---|---|---|---|
| Top-level chrome | `apps/reading/src/AppShell.tsx` | `VERIFIED` | `export function AppShell({ children })` — renders, in order: `<Scene/>` (z-0, first child), the vertical column (`<Topbar/>`, working region, `<NavRail/>`), `<PenguinMascot/>`, `<WindowsLayer/>`, `<HotkeyHud/>`, `<AdBorderMount/>`/`<SceneChrome/>`, `<LemonToastViewport/>`. | The shell frame is `bg-transparent` (SPR-04 landed this) and reserves edges via `--akb-border-inset-*`. **The occlusion the operator saw is in the ROUTE BODIES, not the frame** — landing route roots paint `bg-ice-2 dark:bg-space-2` over the z-0 scene. That is SPR-03's fix, NOT this sprint's. |
| Living mountainscape | `apps/reading/src/scene/Scene.tsx` | `VERIFIED` | `export function Scene({ mood?, fetchScene?, reducedMotion? })`. Root element: `<div data-testid="scene-root" class="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden="true">`. Layers z-0…z-4: ProceduralSky/Peaks, KreaArtLayer, Clouds, Snow, PenguinJourney. | **`assertSceneVisible`'s DOM anchor is `[data-testid="scene-root"]`.** Because it is `aria-hidden` + `pointer-events-none` + `z-0`, pixel-sampling (not DOM presence) is the only honest proof it is *visible* — an opaque route body over it still leaves `scene-root` in the DOM. |
| Scene barrel | `apps/reading/src/scene/index.ts` | **`NEW-to-build`** | Absent on `origin/main`. | **LOAD-BEARING CORRECTION (a):** there is NO `scene/index.ts`. Import the scene from `apps/reading/src/scene/Scene` (`import { Scene } from "./scene/Scene"`), as `AppShell.tsx` already does. Any sprint that writes `from "./scene"` is citing a fiction. |
| Scene chrome | `apps/reading/src/shell/SceneChrome.tsx` | `VERIFIED` | Mounted by `AppShell`; visible chrome over the scene. | Not owned by SPR-01. Listed because `AppShell` imports it (completeness of the render tree). |

---

## 2. Windows (the floating-default surface)

| Concern | Path | Verdict | Key exports / shape | Notes for downstream sprints |
|---|---|---|---|---|
| Windows layer | `apps/reading/src/components/windows/WindowsLayer.tsx` | `VERIFIED` | `export function WindowsLayer()`. **Returns `null` until a window exists in the store** — this is exactly why "no default floating window" is a real v1 gap (anchor #2). | SPR-04 makes a product click open a window by default. `assertWindowOpen` proves the *visible* result. |
| Windows store | `apps/reading/src/workspace/windowsStore.ts` | `VERIFIED` | `export const useWindows` (Zustand); `export const MAX_WINDOWS = 8`; `export const WINDOW_Z_BASE = 40`; `export type WindowMode = "floating" \| "full"`; types `WindowKind`, `WindowRect`, `WorkspaceWindowDescriptor`, `WindowsSnapshot`, `WindowsActions`, `OpenWindowOptions`. | Disjoint from `WorkspaceStore` (the in-page dock/panel slice). A *window* hosts a whole product page; a *panel* is an in-page surface. SPR-04 owns this directory. |
| Products launcher | `apps/reading/src/shell/ProductsLauncher.tsx` | `VERIFIED` | The real launcher button that opens the sub-action surface. **Lives under `shell/`.** | **LOAD-BEARING CORRECTION (b):** `apps/reading/src/components/ProductsLauncher.tsx` is **ABSENT**. The real launcher is `shell/ProductsLauncher.tsx`. A sprint citing `components/ProductsLauncher.tsx` is citing a fiction. |
| Products launcher (the v1 fiction location) | `apps/reading/src/components/ProductsLauncher.tsx` | **`NEW-to-build`** (i.e. does not exist; do NOT create — use the `shell/` one) | Absent on `origin/main`. | Recorded so the lint catches anyone re-introducing the wrong path. The correct one is the `shell/` row above. |

---

## 3. Bottom bar (the labeling surface)

| Concern | Path | Verdict | Key exports / shape | Notes for downstream sprints |
|---|---|---|---|---|
| Nav rail | `apps/reading/src/shell/NavRail.tsx` | `VERIFIED` | Horizontal bottom rail. The home button is `<button aria-label="Antiek home">` wrapping `<IglooMark size={28}/>` — **NO visible "Home" text caption** (product buttons DO carry visible labels). | This is anchor #3: `assertLabeled(page, igloo, "Home")` fails today because there is only an `aria-label`. SPR-07 adds the visible caption + flips it green. |
| Igloo mark | `apps/reading/src/brand/werner/marks/IglooMark` (imported by NavRail as `../brand/werner/marks/IglooMark`) | `VERIFIED` (resolves via NavRail's import) | Default-exported SVG mark; rendered inside the home `<button>`. | Cited via NavRail only; not independently pixel-asserted by SPR-01. |

---

## 4. Hotkeys (the ⌘-scheme surface)

| Concern | Path | Verdict | Key exports / shape | Notes for downstream sprints |
|---|---|---|---|---|
| Shortcut handler | `apps/reading/src/workspace/shortcuts.ts` | `VERIFIED` | `export function installShortcuts(navigate)`, `export function useWorkspaceShortcuts(navigate)`, `export const SHORTCUT_EVENTS`, `export function setCustomHotkeys(...)` / `getCustomHotkeys()`, `export interface CustomHotkeyBinding`. **Contains the `G then I/W/N` vim chords** (the confusing part — anchor #4). | SPR-08 replaces the chords with uniform `⌘`+key. SPR-01 only records the chords' existence; it does not edit this file. |
| Hotkeys barrel | `apps/reading/src/components/hotkeys/index.ts` | `VERIFIED` | Re-exports `KeyChip`, `HotkeyHud`, `AssignHotkey`, `useCustomHotkeys`, the activation contract (`PRODUCT_ACTIVATE_EVENT`, `emitProductActivate`, `makeProductActivateEvent`), the binding tables (`BUILTIN_BINDINGS`, `PRODUCT_BINDINGS`, `SUBACTION_BINDINGS`, `bindingForProduct`, …), and helpers (`normalizeBinding`, `formatBinding`, `detectConflict`, `RESERVED_COMBOS`, …). | The integration seam SPR-07/08/06 import from. SPR-01 only asserts the HUD is on-screen (`assertHotkeyOverlay`). |
| Hotkey HUD | `apps/reading/src/components/hotkeys/HotkeyHud.tsx` | `VERIFIED` | `export function HotkeyHud(props: HotkeyHudProps)` — the "?" cheat-sheet, mounted once by `AppShell`. | `assertHotkeyOverlay` targets this. Whether it is on-screen by default vs toggled is the SPR-08 anchor's concern. |
| Key chip | `apps/reading/src/components/hotkeys/KeyChip.tsx` | `VERIFIED` | `export function KeyChip(props: KeyChipProps)`. | On-control chip; SPR-07/08. |
| Assign hotkey | `apps/reading/src/components/hotkeys/AssignHotkey.tsx` | `VERIFIED` | `export function AssignHotkey(props: AssignHotkeyProps)`. | Per-entity custom `⌘`+key; SPR-08. |
| Bindings | `apps/reading/src/components/hotkeys/bindings.ts` | `VERIFIED` | Binding tables + helpers (see barrel). | SPR-08. |
| Custom hotkeys hook | `apps/reading/src/components/hotkeys/useCustomHotkeys.ts` | `VERIFIED` | `export function useCustomHotkeys()`. | SPR-08. |

---

## 5. Penguin (the character surface)

| Concern | Path | Verdict | Key exports / shape | Notes for downstream sprints |
|---|---|---|---|---|
| Mascot | `apps/reading/src/shell/PenguinMascot.tsx` | `VERIFIED` | The mounted penguin component (cursor-follow + choreography). | SPR-06 rigs the walk-cycle + fixes the white-background emote. Anchor #5 lives on the emote art, not this wrapper. |
| Werner barrel | `apps/reading/src/werner/index.ts` | `VERIFIED` | Re-exports `wernerReducer`, `INITIAL_WERNER_STATE`, `isBusy`, `createWernerStage`, `WADDLE_MS`, `useMouseFollow`, the emote vocabulary, the choreography listener. | The steering/emote layer. |
| Emotes | `apps/reading/src/werner/emotes.tsx` | `VERIFIED` | The emote vocabulary mapped onto animated marks. **The white-background the operator sees is carried by the mark art here**, even though the mascot wrapper is `bg-transparent` — anchor #5. | SPR-06 fixes. |
| Choreography | `apps/reading/src/werner/choreography.ts` | `VERIFIED` | `PRODUCT_ACTIVATE → waddle-to-control` listener + `data-werner-target` click path. | SPR-06. |
| Mouse follow | `apps/reading/src/werner/useMouseFollow.ts` | `VERIFIED` | `export function useMouseFollow(...)` — the ~5s-lagged cursor pursuit. | SPR-06. |

---

## 6. Tokens + ad flanks (the light + declutter surface)

| Concern | Path | Verdict | Key exports / shape | Notes for downstream sprints |
|---|---|---|---|---|
| CSS tokens | `apps/reading/src/design/tokens.css` | `VERIFIED` | `:root` custom props incl. `--sun: #F5DF24` (bold yellow), `--sun-deep`, `--sun-glow`, `--rule: #788596`, `--border: var(--rule)`, `--bar-accent: var(--sun)`, glass tokens. | SPR-09 dials the yellow back to a softer light. SPR-01 must NOT touch this (lint:tokens is the guard). |
| TS tokens | `apps/reading/src/design/tokens.ts` | `VERIFIED` | The TS mirror of the token ramp. | SPR-09. Also an allow-listed raw-hex source for `lint_tokens.ts`. |
| House-ad flank | `apps/reading/src/modes/Reading/HouseSlot.tsx` | `VERIFIED` | `export default function HouseSlot({ promo, onOpen })`; `export interface HousePromoView`, `HouseSlotProps`. Renders a `LemonTag "From the library"` + the promo. | SPR-07 declutters (does not delete — ad economics). |

---

## 7. Backend (Krea) — referenced, not exercised by SPR-01

| Concern | Path | Verdict | Key exports / shape | Notes for downstream sprints |
|---|---|---|---|---|
| Krea routes | `interfaces/research/api/krea_routes.py` | `VERIFIED` | `/krea/scene`, `/krea/generate` (job→poll), `/krea/jobs/{id}`; budget + kill-switch + graceful-absence; operator-auth-gated; `KREA_API_TOKEN` operator-set. | SPR-02 (spike) + SPR-05 (engine). **SPR-01 must NOT depend on a paid stream or a Krea token** (RULE 3): the scene asserts the *procedural* picture, which renders with no token. |

---

## 8. Auth + routing (the harness's login surface)

| Concern | Path | Verdict | Key exports / shape | Notes for downstream sprints |
|---|---|---|---|---|
| Auth context | `apps/reading/src/lib/auth.tsx` | `VERIFIED` | `export function AuthProvider`, `export function useAuth(): { state, refresh, signOut }`. **Contract:** on mount, `AuthProvider` calls `GET ${API_BASE}/auth/me`. `200 { user_id, email, auth_method }` ⇒ `state.status = "authenticated"`; `401` ⇒ `"unauthenticated"`; network error ⇒ `"unauthenticated"`. `RequireAuth` (in `App.tsx`) renders children only when `authenticated`, else `<Navigate to="/login?next=…">`. | **This is the load-bearing fact for the real-app harness.** To get past `RequireAuth` with NO prod app-code bypass, the harness intercepts `GET **/auth/me` at the Playwright network layer and fulfils it with `200 { user_id, email, auth_method }`. No app code is touched. |
| API base | `apps/reading/src/lib/api.ts` | `VERIFIED` | `export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""`. Empty ⇒ same-origin. `apiFetch` sets `credentials: "include"`. | Under `vite preview` with `VITE_API_BASE_URL` unset, `/auth/me` is requested **same-origin** (`<baseURL>/auth/me`). The mock route pattern `**/auth/me` therefore matches. |
| Routes | `apps/reading/src/App.tsx` | `VERIFIED` | `AuthProvider` → `RequireAuth` → `AuthenticatedRoutes` (wrapped in `<AppShell>`). **Default route `/` renders `<ResearchWorkstation/>`.** `/home` renders `<Home/>`. | The harness lands on `/` (a within-contract landing route) authed. |

---

## 9. Test harness (what SPR-01 extends)

| Concern | Path | Verdict | Key exports / shape | Notes |
|---|---|---|---|---|
| Playwright config | `apps/reading/playwright.config.ts` | `VERIFIED` | `testDir: "./e2e"`; one project `chromium`; `baseURL = STORYBOOK_URL ?? http://localhost:6006`; `webServer` boots `storybook-static` on :6006. **Boots Storybook ONLY.** | M5 ADDS a second project (`ams-real`) + a vite-preview `webServer`; it does NOT mutate the Storybook project's `baseURL`. |
| Smoke spec | `apps/reading/e2e/smoke.spec.ts` | `VERIFIED` | Uses `storyUrl(id)` against Storybook. **Contains NO auth/login helper** — `loadStory` loads `iframe.html` story URLs. | **HONESTY CORRECTION:** the brief said "reuse the auth/login helper from `smoke.spec.ts`." It does not exist. `loginAndGotoApp` is therefore `NEW-to-build` (§10), not a reuse. |
| Token lint runner | `apps/reading/scripts/lint_tokens.ts` | `VERIFIED` | `tsx`-run Node script (uses `node:fs`, `import.meta.url`). | The convention the NEW ref-lint mirrors (a `tsx`-run script, no build step). |
| Codegen tooling root | `tools/codegen` | `VERIFIED` | Existing repo tooling dir; the `tools/` convention the NEW `tools/specs/` mirrors. | — |

---

## 10. NEW-to-build deliverables (this sprint + the real-app harness gap)

| Deliverable | Path | Verdict | Who builds it | Shape |
|---|---|---|---|---|
| Anti-fiction ledger | `NEW: docs/ams-v2/verified-interfaces.md` | `NEW-to-build` (this file) | SPR-01 (M1) | This document. |
| Ref-lint | `NEW: tools/specs/verify_spec_refs.ts` | `NEW-to-build` | SPR-01 (M2) | `tsx` script: extracts dependency paths from a sprint HTML page (`.file` chips + inline `<code>` paths), runs `git cat-file -e origin/main:<path>`, exits non-zero if any bare (non-`NEW:`) path is absent; prints a PASS/FAIL/NEW table. |
| Ref-lint negative test | `NEW: tools/specs/verify_spec_refs.test.ts` | SPR-01 (M2) | `NEW-to-build` | Vitest: feeds a fixture citing the v1 fiction `apps/reading/src/components/FloatingSurface.tsx`; asserts the linter reports it ABSENT and exits non-zero. |
| Visible-outcome helpers | `NEW: apps/reading/e2e/_ams/visible.ts` | `NEW-to-build` | SPR-01 (M3) | `assertSceneVisible`, `assertWindowOpen`, `assertLabeled`, `assertHotkeyOverlay`, `assertContrast` + the pure pixel-variance/contrast helpers (unit-testable). |
| Real-app auth + boot helper | `NEW: apps/reading/e2e/_ams/auth.ts` | `NEW-to-build` | SPR-01 (M3) | `loginAndGotoApp(page, route)` — mocks `GET **/auth/me → 200 { user_id, email, auth_method }` via Playwright network interception, then navigates to `route`. **No prod app-code auth bypass.** Records the gap that `smoke.spec.ts` has no such helper. |
| Regression-anchor spec | `NEW: apps/reading/e2e/ams-shell.spec.ts` | `NEW-to-build` | SPR-01 (M4) | 5 `test.fixme` anchors (scene/window/igloo/hotkey/penguin), each naming the owning sprint that flips it green. |
| E2E harness run note | `NEW: docs/ams-v2/e2e-harness.md` | `NEW-to-build` | SPR-01 (M5) | The one command + one env var to run the real-app gate. |
| Real-app auth-mock e2e path | `NEW: apps/reading/e2e/_ams/ (the real-app project)` | `NEW-to-build` | SPR-01 (M3–M5) | **There is no real-app authed e2e path on `origin/main` today** — `playwright.config.ts` boots Storybook only and `smoke.spec.ts` has no login. M3–M5 build that path (vite-preview `webServer` + `ams-real` project + auth mock). |

### Confirmed-absent fictions (the lint must catch these)

| Fictional path | Status | Real replacement |
|---|---|---|
| `apps/reading/src/scene/index.ts` | ABSENT | import from `apps/reading/src/scene/Scene` |
| `apps/reading/src/components/ProductsLauncher.tsx` | ABSENT | `apps/reading/src/shell/ProductsLauncher.tsx` |
| `apps/reading/src/components/FloatingSurface.tsx` | ABSENT (v1 fiction) | none — never existed; windows live in `components/windows/` |
| `apps/reading/src/components/SubActionLauncher.tsx` | ABSENT (v1 fiction) | none — the launcher is `shell/ProductsLauncher.tsx` |

---

## 11. SPR-10 as-built reconciliation (the loop closed)

> Sections 1–10 record what SPR-01 *anticipated* each sprint would do (the
> forward-looking ledger). All ten sprints are now merged into
> `caffen/AMS2-integration`; this section reconciles the ledger to the **as-built**
> reality so the spec matches the code that shipped (the anti-fiction fix). Each
> row was re-checked on the merged branch. **Zero fictional interfaces survive.**

| Claim / anticipation | As-built reality (merged branch) | Verdict |
|---|---|---|
| The default route renders `ResearchWorkstation` | It is `apps/reading/src/modes/ResearchWorkstation/index.tsx` (the SPR-03 sprint page mis-cited `ResearchWorkstation.tsx`, which does NOT exist — index.tsx is the entry; idle `/` renders `<StartResearch embedded/>`, whose bg-free root reveals the scene in the margins). | RECONCILED |
| SPR-05 builds a streaming frame source (`NEW: useSceneStream.ts`) | **NOT created.** SPR-02 returned NO-GO; the existing `SceneFetcher` type (`apps/reading/src/krea/useKreaScene.ts`) **is** the §4 frame-source seam. A "stream" hook on a NO-GO would be fiction. The shipped engine is the 60 fps procedural floor + periodic mood-gated Krea art. | RECONCILED (honest NO-GO) |
| A streaming route extends `krea_routes.py` | **No streaming route added.** The `/krea` namespace stays exactly `/krea/scene`, `/krea/generate`, `/krea/jobs/{id}` — enforced by `interfaces/research/api/test_krea_stream.py`. | RECONCILED |
| `shortcuts.ts` "contains the `G then I/W/N` vim chords" (§4) | **Chords removed (SPR-08).** Uniform `⌘+key`: products are `⌘O` (home, `mod+o`) / `⌘I` (more, `mod+i`) / per-product combos from `SAFE_ASSIGNABLE` (a–z minus `RESERVED_COMBOS`); `chipBindings()`/`bindingForProduct` expose the binding→label map; `isWithinRange` gates custom assignment. No-chord grep guard = 0. | RECONCILED |
| Tokens soften the yellow (SPR-09) | Softened **var-deep only** (`tokens.css`/`tokens.ts`): `--sun`/`--bar-accent` kept loud (`#F5DF24`), accents re-toned + a new `--sun-light` ramp, AA preserved. `tailwind.config.js` mirror NOT re-toned (out of SPR-09 scope) — see the verification report §4 follow-up. | RECONCILED (with disclosed follow-up) |
| Experience proof | Consolidated in `apps/reading/e2e/ams-v2-experience-matrix.spec.ts` (9 criteria, 1 operator-only `test.fixme`) + `ams-v2-resilience-matrix.spec.ts` (criterion #9). Full `ams-real` suite 37 green. All 5 regression anchors un-fixme'd + green. | RECONCILED |

The v1 fictions (`#scene-root`, `FloatingSurface`, `SubActionLauncher`) remain
confirmed-absent (§ above); the ref-lint keeps that class of error mechanically
impossible.

---

_Seeded by SPR-01 (Grounding + experience-gate harness) 2026-05-31; **finalized +
reconciled to the as-built code by SPR-10 (integration + experience-proof +
write-back) 2026-06-01.** Every `VERIFIED` row is re-checkable with
`git cat-file -e caffen/AMS2-integration:<path>`; run
`tsx tools/specs/verify_spec_refs.ts <sprint.html>` to lint a sprint page against this reality._
