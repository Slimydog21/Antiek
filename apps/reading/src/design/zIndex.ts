/**
 * zIndex.ts — the single named z-index ladder (FEEL-S2, Dim 10).
 *
 * PostHog's stacking discipline is ONE named ladder: a layer's elevation is
 * declared once, with a name and a documented purpose, in a single place a
 * designer can reason about — instead of grepping for `z-[137]`. PostHog ships
 * it as CSS custom properties (`--z-raised`, `--z-popover`, `--z-modal`,
 * `--z-toast`).
 *
 * THIS module is the central catalog + drift-tripwire — NOT yet the full
 * call-site migration. The runtime z-bases (`windowBase`, `floatingPanelBase`)
 * are sourced from it; the remaining `z-[100]`/`z-[200]` Tailwind literals are
 * catalogued + pinned (table below) so a future pass migrates them to named
 * values from one source. "No magic numbers at call sites" is the destination;
 * what ships today guarantees the numbers can't silently drift apart.
 *
 * Antiek had grown the opposite: the same elevations were re-declared as
 * per-store magic constants and per-component Tailwind `z-[…]` literals
 * (`WINDOW_Z_BASE = 40` here, `FLOATING_Z_BASE = 2` over in elevation.ts,
 * `z-[100]` in LemonModal, `z-[200]` in LemonToast, `z-[150]` in AdBorder…).
 * Nothing tied them together; nothing caught a drift that would let a toast
 * slide under a modal.
 *
 * This module is that one place. It is a PURE CONSOLIDATION: every number
 * below is the EXACT value the codebase already uses today — re-exported under
 * a name with its purpose, not changed. Behaviour is identical; what's new is
 * that the ladder is now (a) centrally readable and (b) pinned by
 * `zIndex.test.ts` so a future edit that reorders the stack is caught.
 *
 * ── How the ladder maps to today's call sites (the audit, value-for-value) ──
 *
 *   name              value   today's source (unchanged)
 *   ──────────────    ─────   ─────────────────────────────────────────────
 *   scenePresence        1    BrainPresence.tsx inline `zIndex: 1` — one notch
 *                             over the scene floor; ties with `raised` (see
 *                             the rung's doc comment for why the tie is safe)
 *   raised               1    docked panel raised over dock chrome (z=0→1)
 *   floatingPanelBase    2    elevation.ts `FLOATING_Z_BASE`; WorkspaceStore
 *                             "Floating panels: z = 2…50 (via zCounter)"
 *   sceneBadge           5    SceneStatusBadge.tsx (ALC SPR-03, PR 144) — was a
 *                             bare `zIndex: 5`, now catalogued here
 *   floatingPanelCeiling 50   WorkspaceStore / README "z = 2…50" upper edge
 *   windowBase          40    windowsStore.ts `WINDOW_Z_BASE`
 *   mobileRail          40    NavRail mobile overlay rail — was a `z-40`
 *                             Tailwind literal; ties with `windowBase`
 *   mobileRailToggle    50    NavRail collapsed hamburger — was a `z-50`
 *                             literal; ties with `floatingPanelCeiling`
 *   mascot              60    MascotStation.tsx `z-[60]`
 *   modal              100    LemonModal.tsx `z-[100]`
 *   popover            120    Notebook/SlashMenu.tsx `z-[120]`
 *   adOverlay          150    AdBorder.tsx `z-[150]`
 *   toast              200    LemonToast.tsx `z-[200]`
 *   tooltip            250    Tooltip.css `[data-tip]::after` (new, W2)
 *
 * Surfaces whose elevation is a Tailwind class (LemonModal/LemonToast/
 * AdBorder/SlashMenu/MascotStation) are NOT rewired here — those classes are
 * tailwind/token territory (Builder-A) and a class→inline-style swap would be
 * a behaviour change, not a consolidation. They are catalogued in this ladder
 * as the canonical named values so a future token pass has one source to read
 * and `zIndex.test.ts` already pins their numbers against drift.
 */

/**
 * The named z-index ladder. Frozen so a value can't be mutated at runtime;
 * a deliberate change must edit this object AND the pin in `zIndex.test.ts`.
 *
 * Read top-to-bottom = bottom-of-stack to top-of-stack. The ordering here IS
 * the layering contract (see `FEEL_CONTRACT.md` layer diagram).
 */
export const zIndex = Object.freeze({
  /**
   * BrainPresence — the ambient low-opacity brain drifting behind app content.
   * One notch over the living scene floor (Scene is `z-0`), below every piece
   * of chrome. The value ties with `raised` because both rungs mean "one above
   * a local z=0 floor" — and the tie is safe: BrainPresence is `aria-hidden` +
   * `pointer-events: none`, mounted in AppShell BEFORE the content column, so
   * on equal z the DOM order still paints docked chrome above it.
   */
  scenePresence: 1,
  /** A docked panel raised one notch over the dock chrome (dock chrome = 0). */
  raised: 1,
  /**
   * First z assigned to a floating WorkspaceStore panel. The store's monotonic
   * `zCounter` walks UP from here as panels are focused. Mirrors
   * `elevation.ts FLOATING_Z_BASE` (which the shadow-depth math reads).
   */
  floatingPanelBase: 2,
  /**
   * Scene fallback-status badge (SceneStatusBadge, ALC SPR-03, PR 144). A small
   * operator observability chip painted over the scene floor (z≈0) and above a
   * floating panel's base, but well below a workspace window — the reader must
   * see "live art is off" without it competing with real chrome. Catalogued
   * here (was a bare `zIndex: 5` literal) so it can't silently drift.
   */
  sceneBadge: 5,
  /** Top of the floating-panel band ("z = 2…50") — documents the headroom. */
  floatingPanelCeiling: 50,
  /**
   * Base z for a workspace *window* (windowsStore). A window always paints
   * over the scene (z≈0) but under the in-page modal/toast stack. Re-exported
   * as `WINDOW_Z_BASE` from windowsStore.ts for back-compat.
   */
  windowBase: 40,
  /**
   * Mobile (sm/md tier) NavRail as an absolute overlay over the working
   * region — was a `z-40` Tailwind literal on the rail `<aside>`. The value
   * ties with `windowBase` deliberately: the pre-consolidation `z-40` put the
   * rail at the window-band base, so a mobile window and the rail interleave
   * exactly as they did before (same z → DOM order decides). Conditionally
   * applied (mobile only); the desktop rail is in-flow and carries no z.
   */
  mobileRail: 40,
  /**
   * The collapsed-state mobile nav toggle (the hamburger that reopens the
   * rail) — was a `z-50` Tailwind literal. It must stay tappable above the
   * whole floating-panel band, so it sits at the band's ceiling; the value
   * ties with `floatingPanelCeiling`.
   */
  mobileRailToggle: 50,
  /** Draggable Mascot — floats above panels/windows, below modals. */
  mascot: 60,
  /** LemonModal scrim + dialog — above all in-page surfaces. */
  modal: 100,
  /** Slash / command popover menus — must sit above an open modal. */
  popover: 120,
  /** Full-bleed ad border overlay (pointer-events-none) over the modal layer. */
  adOverlay: 150,
  /** LemonToast stack — nothing but a tooltip occludes a toast. */
  toast: 200,
  /**
   * The CSS-only tip (components/Tooltip.css) — the top of the ladder. A tip
   * explains the control under the pointer or focus, so it must read over any
   * layer that control can sit in, a toast's dismiss button included.
   */
  tooltip: 250,
} as const);

export type ZIndexLayer = keyof typeof zIndex;

/**
 * The ladder in bottom-to-top stacking order. This is the canonical
 * ordering used by `zIndex.test.ts` to assert monotonicity. Keep this array
 * in sync with the visual stack, NOT with declaration order of `zIndex`.
 * Adjacent rungs may TIE in value only where the rungs' doc comments record
 * why the tie is safe (disjoint stacking contexts / a documented band edge);
 * the test pins the exact set of ties so no new one can sneak in.
 */
export const Z_LADDER_ORDER = [
  "scenePresence",
  "raised",
  "floatingPanelBase",
  "sceneBadge",
  "windowBase",
  "mobileRail",
  "floatingPanelCeiling",
  "mobileRailToggle",
  "mascot",
  "modal",
  "popover",
  "adOverlay",
  "toast",
  "tooltip",
] as const satisfies readonly ZIndexLayer[];

/**
 * Escape hatch: the smallest z that paints strictly above `base`.
 *
 * This is the named form of the `zCounter + 1` "raise above the current top"
 * pattern the workspace stores already use when a panel/window is focused.
 * Prefer a named ladder layer; reach for `forceAbove` only for the dynamic
 * "stack me one above whatever is currently on top" case, so the intent reads
 * at the call site instead of a bare `+ 1`.
 */
export function forceAbove(base: number): number {
  return base + 1;
}
