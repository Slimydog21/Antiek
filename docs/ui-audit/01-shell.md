# 01 — Shell & Navigation

Audited against `src/design/DESIGN_LANGUAGE.md` + `FEEL_CONTRACT.md` first, general
craftsmanship second. `npm run lint:tokens` and `npm run lint:type` both pass
(80/120 hex grandfathered, 1 type grandfathered) — so everything below is either
grandfathered debt or a class of problem the lints do not see (dead utilities,
phantom hotkeys, dead controls, off-ladder z, divergent motion).

One probe result frames several findings: `text-ink-mute`, `text-ink-soft`, and
`text-danger` are **not defined** in `tailwind.config.js` (verified with a probe
build — Tailwind emits no CSS for them; `text-shadow-1`, `text-emperor`,
`border-rule`, `bg-glass` from the same probe do emit). They are used 630 times
across 146 files app-wide, including most shell files below. In day mode the
muted hierarchy silently renders as inherited ink; error text silently loses its
red.

## Surfaces

### App route registry — `src/App.tsx`
Route table + auth gating only. `RequireAuth` (App.tsx:78) renders a token-clean
loading veil (App.tsx:83, ice-2/space-2, mono uppercase) and redirects with
`?next=` preserved. `/login`, `/trust`, `/speak/invite/:token`, `/speak/browse`
are unauthenticated; `/_panel/:panelId` renders PanelWindowApp outside the shell.
Loading state exists; no error state for auth (a failed `/auth/me` that isn't 401
has no surface).

### AppShell — `src/AppShell.tsx` (+ `.stories.tsx`, `.spr06.test.tsx`, `.hotkeys.test.tsx`)
The chrome frame (AppShell.tsx:101-199): transparent seam frame reading the four
`--akb-border-inset-*` vars, z-0 `<Scene/>` + `<BrainPresence/>`, vertical column
of Topbar → working region (PanelLayout wrapping SceneChrome + WindowsLayer) →
bottom NavRail, then PenguinMascot, AdBorderMount, LemonToastViewport, HotkeyHud.
Shortcuts + workspace hydration + toast-navigation bridge mounted once here.
Stories cover Empty + WithProjectTree and carry the `a11y-audit` tag.

### NavRail — `src/shell/NavRail.tsx`
Bottom rail (SPR-06 default; vertical `left` kept for stories/rollback): sun-bg
BrainMark home button with visible caption + ⌘ chip, Search (⌘K), the four
workflow doors from `WORKFLOW_ORDER` (active = bg-sun slab + ink marker on the
inner edge), attention badge on Research, More → ProductsLauncher. Ink rail with
`border-t-edge border-sun` (NavRail.tsx:454). Mobile collapses to a hamburger
(NavRail.tsx:313-327). Hotkey chips read live from `bindings.ts` — no hand-typed
combos.

### Topbar — `src/components/navigation/Topbar.tsx`
44px bar: route-derived breadcrumbs (hand-maintained `known` label map,
Topbar.tsx:31-63) + account LemonDropdown. Deliberately no search box.

### SceneChrome — `src/shell/SceneChrome.tsx`
Per-workflow chrome above the route view: workflow label, action verbs from the
`SCENES` registry (SceneChrome.tsx:65-124), in-scene tabs, optional
ThreadBreadcrumb row. Body is glass (`bg-glass backdrop-blur-glass`,
SceneChrome.tsx:267). Unbuilt workflows render WorkflowStub.

### ProductsLauncher — `src/shell/ProductsLauncher.tsx`
The "More" overlay: fixed centered 760px card (role=dialog, aria-modal) with
filter input, featured Home row, workflow deep-mode groups, "Run & settings"
bucket, honest dimmed `not yet` LemonTags, ⊞ open-in-window affordances, and a
mono footer ("Esc to close · ⌘K for deep search"). Keyboard: arrows + Enter on a
highlight index (no roving focus), Esc closes, scrim-click closes.

### PanelWindowApp — `src/PanelWindowApp.tsx`
The popout OS-window app (`/_panel/:panelId`): BroadcastChannel hand-off, own
document.title, error state (PanelWindowApp.tsx:93-105), loading state
(:107-113), and a slim 36px title strip mimicking PanelHandle (:119-126).

### Panel system — `src/workspace/PanelLayout.tsx`, `PanelLayoutPanel.tsx`, `PanelHandle.tsx`, `PanelHost.tsx`, `PanelRegistry.tsx`
Left/right 320px docks + resizable bottom dock + floating layer; tier-sm splash
(PanelLayout.tsx:91-104); dock auto-collapse toast on tier-lg. Floating panels =
opaque-chunky contract (border-edge border-sun, rounded-hog,
`opaquePanelShadowClasses`, focus outline-sun, framer-motion spring in/out,
ESC-to-close, in-panel Tab trap). PanelHandle: drag grip, pin ★/☆, LemonDropdown
kebab with hotkey hints, quick-close ✕, bottom-right resize grip. PanelHost =
route-level starter panels; PanelRegistry = lazy PanelKind map.

### Window chrome — `src/components/windows/WorkspaceWindow.tsx`, `WindowsLayer.tsx`, `SubActionList.tsx`
Glass scene windows (FEEL LAYER A): title-bar-only depth shadow via
`shadowForStackDepth`, glass body that pauses blur when unfocused, opaque when
full; drag/resize reuse the panel clamp; keyboard move/resize/Enter/Escape on the
title bar; WindowAdBorder insets. WindowsLayer = one absolute layer with
AnimatePresence + a registered-renderer error state (WindowsLayer.tsx:54).

### PenguinMascot — `src/shell/PenguinMascot.tsx`
The ratified fixed-station mascot: BrainMascot + emote overlay + wander/waddle
CSS, single-click floats ProjectTree, double-click opens /home, drag re-stations
(clamped), SPR-10 directed choreography walks him to activated controls and home
again. `z-[60]` = catalogued `zIndex.mascot`. Reduced-motion still floor
throughout.

### ProjectTree — `src/shell/ProjectTree.tsx`
Workflow-scoped content tree (Pinned / Recent / All), live investigation +
document data, status LemonTag dots, ⌘-click opens as floating panel. Loading,
error, and empty states all present.

### WorkflowStub — `src/shell/WorkflowStub.tsx`
The honest "not yet" surface, keyed to taxonomy `built` flags, with a loud misuse
guard and pending-mode list. Serif headline, mono kickers.

### ThreadBreadcrumb / ThreadJump — `src/shell/ThreadBreadcrumb.tsx`, `ThreadJump.tsx`
Cross-workflow trail in mono 12.5px; forked-thread integrity warning (role=alert)
instead of a lying trail; unbuilt hops dimmed + non-navigable.

### GlassSurface — `src/shell/GlassSurface.tsx`
The landing-glass primitive: consumes glass tokens, owns the WCAG-AA scrim
(`SCRIM_MIN_OPACITY 0.2`, GlassSurface.tsx:73), degrades to solid under
reduced-motion/no-scene. The reference implementation other surfaces should use.

### Hotkey treatment — `src/workspace/shortcuts.ts`, `src/components/hotkeys/{bindings.ts,KeyChip.tsx,KeyChip.css,HotkeyHud.tsx,HotkeyHud.css}`
Uniform ⌘+key scheme (chords removed), custom per-entity bindings with
conflict detection + reload persistence, `?` HUD on LemonModal, always-visible
KeyChips on rail doors. KeyChip.css paints from CSS vars (`--ink`, `--card`,
`--text-muted`) — token-clean.

### Home — `src/modes/Home/Home.tsx`
The /home front door: GlassSurface landing, BrainMascot, serif H1 + lede, four
door cards read from the taxonomy (label + route) with a local verb line, and a
featured biography section with its own CTA.

## Findings

| Severity | Location (file:line) | Issue | Fix direction |
|---|---|---|---|
| P0 | ProjectTree.tsx:244 (also PanelHandle.tsx:147,154,166,263; ProductsLauncher.tsx:226,318; SceneChrome.tsx:201; Topbar.tsx:85,89; ThreadBreadcrumb.tsx:51,69,88,97; PanelWindowApp.tsx:99,123; WorkflowStub.tsx:55,73,88,97 — 630 uses / 146 files app-wide) | `text-danger`, `text-ink-mute`, `text-ink-soft` are **undefined Tailwind utilities** — no CSS is emitted (probe-verified against tailwind.config.js). The muted-text hierarchy silently renders as inherited ink in day mode; the ProjectTree load-error text is not red. | Add `ink-mute`/`ink-soft`/`danger` keys to the tailwind color map mirroring tokens (shadow-1 / shadow-2 / emperor, with night partners), or sweep-rename to existing tokens. One fix, app-wide effect. |
| P0 | PanelHandle.tsx:192,202,212,222,232 (vs shortcuts.ts:310-350, bindings.ts:283-287) | Kebab hotkey hints are phantom: `⇧⌘B`, `⌃⌘B`, `⌥⌘F`, `⌥⌘P` have no handler anywhere; `⌘B` is shown as "Dock left" but actually toggles the ProjectTree panel. The HUD's Panels group (bindings.ts:283-287) proves the real set. Lying chrome — violates the function/honesty contract. | Either implement the four mode-switch bindings in shortcuts.ts + bindings.ts (preferred — the hints are good), or strip the hints. Never let LemonMenuItem `hint` be hand-typed: feed from bindings.ts like NavRail does. |
| P0 | SceneChrome.tsx:69 (same pattern CommandPalette.tsx:568) | The Research scene's "Ask" action dispatches `AISIDECAR_TOGGLE` — **no production listener exists** (only HELP_TOGGLE has one; shortcuts.ts:200 only *dispatches* it). The primary action bar carries a dead verb. | Route through `useWorkspace.open("AISidecar", …)` exactly like `toggleAISidecar` (shortcuts.ts:189-201), or dispatch PALETTE-style events only where a listener exists. |
| P0 | Topbar.tsx:123-130 | Account menu items Profile / Settings / Sign out only call `close()` — no navigation, no sign-out. Three dead controls in the top-level chrome. | Wire Settings → navigate("/settings"); Sign out → the auth client's logout; either implement Profile or cut it (honesty contract). |
| P0 | ProductsLauncher.tsx:198,205 (vs components/lemon/LemonModal.tsx:103,125) | The launcher is a `role=dialog aria-modal` overlay with **off-system modal chrome**: `z-50` (below the mascot at z-60 — the penguin floats *over* the dialog), `border border-rule rounded-lg shadow-2xl` (default Tailwind soft shadow, 8px radius) while its sibling HotkeyHud via LemonModal gets `z-[100] border-edge border-sun rounded-hog-lg shadow-lift`. It also lacks LemonModal's focus trap, scroll-lock, and restore-focus despite claiming "keyboard parity" (ProductsLauncher.tsx:58-62). Two overlay idioms side by side. | Rebuild the launcher card on LemonModal (or extract its chrome), which fixes z (ladder `modal`=100), chunky shadow, radius, and the focus trap in one move. |
| P1 | Home.tsx:92-97,136-140 | Door cards + biography CTA roll their own motion (`transition` + `hover:shadow-z2 hover:-translate-y-0.5`) instead of motion.ts `press`/`cardLift`, and omit `dark:shadow-z*-night` — at night the chunky ink shadow is invisible on charcoal, so the depth system silently disappears on the front door. | Swap to `cardLift` (cards) / `press` (CTA) from design/motion.ts; they carry the night variants. |
| P1 | SceneChrome.tsx:267 | The scene body hand-rolls `bg-glass backdrop-blur-glass` and **skips GlassSurface**, the one primitive that owns the AA scrim (GlassSurface.tsx:73,176-191). The inline comment claims the frost+blur keeps AA, which is exactly the assumption GlassSurface exists to not make. | Wrap the body in `<GlassSurface>` (or adopt its scrim layer) so the legibility contract has one owner. |
| P1 | PanelHandle.tsx:285 | Resize grip hardcodes `#F5DF24` ×4 in a gradient — the four grandfathered baseline entries for this file; policy says the baseline only shrinks. | Use `var(--sun)` in the gradient; baseline drops by 4. |
| P1 | PanelLayoutPanel.tsx:148-152 vs WorkspaceWindow.tsx:261 | Two hand-tuned framer-motion springs for the same "surface arrives" gesture (320/28 vs 320/30), while motion.ts ships an unwired `enter` primitive. Interaction physics diverge per layer. | Pick one spring spec (or wire `enter`) in elevation/motion and consume from both. |
| P1 | Topbar.tsx:31-63 | Breadcrumb labels come from a hand-maintained `known` map that has drifted from the route table: /home, /my-research, /write, /speak, /library, /readings, /meta-readings, /biography, /deep-research, /coordination… render as raw URL segments ("my-research", lowercase, hyphenated) in the top chrome. | Derive labels from workflowTaxonomy/route metadata (the drift-checked source), or extend the map as a stopgap. |
| P1 | Topbar.tsx:80; SceneChrome.tsx:179; PanelLayout.tsx:131,159,185; PanelWindowApp.tsx:119 | Border-contract ambiguity: tokens.ts `rule` (AMS-SPR-01) "retires yellow from the default border role", yet static chrome edges (topbar, action bar, dock frames, popout header) all use `border-sun`. FEEL_CONTRACT sanctions sun on floating chunky cards; whether static chrome counts is undocumented. DESIGN_LANGUAGE.md §5.6 ("sun-yellow edge") and tokens.ts currently tell two stories. | Adjudicate once in DESIGN_LANGUAGE.md: either chrome edges move to `border-rule` (sun reserved for bar + floating cards + Werner), or record sun-edges-on-chrome as the ratified rule. |
| P1 | NavRail.tsx:320,455 | Off-ladder z: mobile rail `z-40` sits exactly on `zIndex.windowBase` (40) so the mobile rail can interleave with workspace windows; the collapsed hamburger `z-50` equals `floatingPanelCeiling`. Neither is in the named ladder (zIndex.ts:62-97). | Add a named `mobileRail` rung to zIndex.ts and consume it. |
| P2 | SceneChrome.tsx:198,225; Topbar.tsx:85; PanelHandle.tsx:154; WorkspaceWindow.tsx:294; ThreadBreadcrumb.tsx:51,69 | `text-[12.5px]` — fractional, off the named scale (xxs 10 / xs 12 / sm 14) — is the de-facto chrome size, hand-arbitrated in 6+ files. | Promote a named token (e.g. `xs+` 12.5 or settle on xs/sm) and sweep. |
| P2 | ProjectTree.tsx:195,203; ProductsLauncher.tsx:251,322,374; Home.tsx:102,125; SubActionList.tsx:132; NavRail.tsx:223,232,363 | More off-scale sizes: `text-[13px]`, `text-[10.5px]`, `text-[13.5px]`, `text-[9px]` (badge — below the 10px xxs floor), `text-[10px]` captions with `leading-[11px]`. | Same named-scale sweep; badge/caption sizes deserve one xxs-with-tight-leading token. |
| P2 | PanelLayout.tsx:63-65 | Dock transition uses raw `duration-150 ease-out` instead of the named `duration-base`/`ease-standard` motion tokens the config provides. | `duration-base ease-standard` (or document why docks differ). |
| P2 | PanelHandle.tsx:149,172,263; WorkspaceWindow.tsx:292,305,315; ProjectTree.tsx:339; Topbar.tsx:119; NavRail.tsx:107-141 | Mixed icon idioms across shell chrome: single-path SVGs (NavRail), unicode glyphs (⋮⋮ ★ ☆ ✕ ❐ ▢), an emoji (📄, 👤). Three visual languages for the same chrome register. | Extend the NavRail 24-grid SVG idiom to panel/window/tree chrome; drop emoji from chrome. |
| P2 | ProductsLauncher.tsx:405 | Footer prints "Esc to close · ⌘K for deep search" as plain text while the rail + HUD render KeyChips. | Render KeyChips for Esc / ⌘K. |
| P2 | App.tsx:119 | `lm-loading` class has no CSS definition anywhere — the LinkMonster Suspense fallback is unstyled (also off-voice next to App.tsx:83's styled loading veil). | Style it like the RequireAuth veil or drop the dead class. |
| P2 | PanelWindowApp.tsx:119-126 vs PanelHandle.tsx:131-156 | The popout title strip is a near-copy of PanelHandle with divergent geometry/typography (h-9, `text-[12px]` vs the handle's `text-[12.5px]`). Two window-title treatments to keep in sync forever. | Extract a shared TitleStrip, or make the popout render PanelHandle in a non-drag mode. |
| P2 | NavRail.tsx:464,468 | Rail dividers use `border-white/10` — a default-palette alpha white, not a token (the token lint only greps hex, so it passes). | A `--rule-on-ink` token or `border-ice-0/10` (token-derived). |
| P2 | Home.tsx:66 | `text-3xl` (30px) on the Home H1 exceeds the 24px chrome ceiling; lint_type_scale.ts documents named utilities as an accepted unscanned residual. Defensible as landing "content", but it is the app's front door — adjudicate. | Keep (record as content) or drop to `text-2xl`. |
| P2 | PanelLayoutPanel.tsx:194 | Docked panels carry `min-h-[140px]` — an arbitrary magic minimum, unshared with any token/constant. | Named constant with a one-line rationale. |
| P2 | WindowsLayer.tsx:33 | Layer container `z-30` is off-ladder (windows set their own inline z from WINDOW_Z_BASE, so it works, but 30 appears in no ladder). | Consume a named rung or document the container as z-agnostic. |
| P2 | NavRail.tsx:434; AISidecar.tsx:262 | Stale comments: NavRail references the removed `g m` chord; AISidecar claims an `antiek:aisidecar:toggle` "event handler… routes through the workspace" — no such listener exists (see the dead-Ask P0). | Update both comments when the P0 is fixed. |
| P2 | tokens.ts:34-46 | The sun-deep/sun-glow drift comment describes the Tailwind mirror as unfixed ("OUT OF SCOPE… no CI guard"), but tailwind.config.js:32-33 already points those keys at the CSS vars. Stale contract documentation. | Reword the block to record the fix. |

## Verdicts

### App.tsx — bring to standard:
1. Fix or remove the undefined `lm-loading` fallback class (App.tsx:119).
2. Give the auth veil the named type size (text-xs) instead of `text-[12px]` (App.tsx:83).

### AppShell.tsx — bring to standard:
1. Nothing structural — the frame, seam, layering, and mount-once discipline all match the contract. Sweep its children per their own verdicts; the shell inherits their fixes.

### NavRail — bring to standard:
1. Add a named `mobileRail` z-rung and replace `z-40`/`z-50` (NavRail.tsx:320,455).
2. Replace `border-white/10` dividers with a token-derived hairline (NavRail.tsx:464,468).
3. Fold badge/caption sizes (`text-[9px]`, `text-[10px]`/`leading-[11px]`) into named scale tokens (NavRail.tsx:223,232).
4. Refresh the stale `g m` comment (NavRail.tsx:434).

### Topbar — bring to standard:
1. Wire or cut the three dead account-menu items (Topbar.tsx:123-130).
2. Fix the breadcrumb label drift — derive from taxonomy or extend the map (Topbar.tsx:31-63).
3. Replace dead `text-ink-soft`/`text-ink-mute` once the color tokens exist; resolve the sun-vs-rule border question.

### SceneChrome — bring to standard:
1. Fix the dead "Ask" verb — open the AISidecar panel through the workspace store (SceneChrome.tsx:69).
2. Adopt GlassSurface (or its scrim) for the glass body (SceneChrome.tsx:267).
3. Move action/tab text off `text-[12.5px]`; resolve the border-sun question (SceneChrome.tsx:179).

### ProductsLauncher — bring to standard:
1. Rebuild on LemonModal chrome: fixes z-50-under-mascot, soft `shadow-2xl`/`rounded-lg`/`border-rule`, and the missing focus trap in one move (ProductsLauncher.tsx:198,205).
2. KeyChips in the footer (ProductsLauncher.tsx:405).
3. Named type sizes for rows/headers (ProductsLauncher.tsx:239,251,265,322).

### PanelWindowApp — bring to standard:
1. Share the title-strip treatment with PanelHandle (geometry + 12px vs 12.5px title) (PanelWindowApp.tsx:119-126).
2. Fix dead `text-ink-mute` uses with the new tokens (PanelWindowApp.tsx:99,123).
3. Otherwise good: real loading + error states, honest copy, token-clean surfaces.

### Panel system (PanelLayout / PanelLayoutPanel / PanelHandle / PanelHost / PanelRegistry) — bring to standard:
1. Fix the phantom kebab hotkey hints — implement the bindings or strip the hints; feed hints from bindings.ts (PanelHandle.tsx:190-250).
2. Migrate the resize-grip `#F5DF24` gradient to `var(--sun)`; shrink the baseline by 4 (PanelHandle.tsx:285).
3. Unify the arrive-spring with WorkspaceWindow (or wire motion.ts `enter`) (PanelLayoutPanel.tsx:148-152).
4. Named motion tokens for the dock transition (PanelLayout.tsx:63-65); name the `min-h-[140px]` (PanelLayoutPanel.tsx:194).
5. Fix dead `text-ink-mute` (PanelHandle.tsx:147,154,166,263).

### Window chrome (WorkspaceWindow / WindowsLayer / SubActionList) — bring to standard:
1. Unify the enter spring with floating panels (WorkspaceWindow.tsx:261).
2. Named type size for the window title (WorkspaceWindow.tsx:294); SVG icon idiom for ❐/▢/✕/⋮⋮ (WorkspaceWindow.tsx:292,305,315).
3. Resolve the `z-30` container against the ladder (WindowsLayer.tsx:33).
4. Otherwise the FEEL glass-scene contract (title-bar-only depth shadow, blur pausing, clamp reuse, focus restore) is faithfully implemented.

### PenguinMascot — waive:
Ratified interaction model with a documented still floor, catalogued z, and clamped geometry; its CSS lives in the sanctioned werner/mascot homes. No contract issues found.

### ProjectTree — bring to standard:
1. `text-danger` on the error state renders nothing — the tree's only error surface is invisible-as-error (ProjectTree.tsx:244). Fix via the new tokens.
2. Replace dead `text-ink-mute` (ProjectTree.tsx:216,240,248,352,370) and off-scale sizes (195,203).
3. Replace the 📄 emoji with the SVG idiom (ProjectTree.tsx:339).

### WorkflowStub — waive:
Honest-empty contract fully implemented (data-driven build presence, loud misuse guard); only dead-class/off-scale sizes, covered by the global sweeps.

### ThreadBreadcrumb / ThreadJump — waive:
Integrity-warning honesty, correct roles, mono idiom consistent with Topbar; only the dead `text-ink-mute`/`text-ink-soft` sweep applies.

### GlassSurface — waive:
It is the reference primitive; the finding is that SceneChrome doesn't use it.

### Hotkey treatment (shortcuts / bindings / KeyChip / HotkeyHud) — bring to standard:
1. The binding *tables* are honest; the lies live in PanelHandle's hand-typed hints (fixed there) and the unwired AISIDECAR_TOGGLE event (fixed in SceneChrome).
2. KeyChip/HotkeyHud themselves are token-clean, LemonModal-based, chord-free as documented. Waive the components; the two wiring fixes above are the whole verdict.

### Home — bring to standard:
1. Adopt motion.ts `cardLift`/`press` + night shadow variants on door cards and the CTA (Home.tsx:92-97,136-140).
2. Adjudicate the 30px H1 against the 24px chrome ceiling (Home.tsx:66).
3. Off-scale `text-[13.5px]`/`text-[15px]` → named sizes (Home.tsx:102,125).
4. GlassSurface usage, taxonomy-driven doors, and voice discipline are exactly the contract — keep.
