/**
 * zScale.ts — the single documented z-index scale for the mountain shell (ALC SPR-08 M1).
 *
 * WHY THIS FILE EXISTS (F-1, and the F-2 it prevents)
 * ---------------------------------------------------
 * Before SPR-08 the shell's z-indices were 12 scattered literals across
 * shell/, scene/, components/windows/, components/lemon/, and werner/ (NavRail
 * z-40/z-50, WindowsLayer z-30 + WINDOW_Z_BASE 40, PenguinMascot z-[60],
 * LemonModal z-[100], LemonToast z-[200], …). The order was "correct by
 * construction" on DESKTOP but UNCONFIRMED in a real browser — and it was NOT
 * correct on MOBILE: the bottom NavRail becomes `position:absolute z-40` on the
 * sm/md tiers (NavRail.tsx), which TIES the windows layer's `WINDOW_Z_BASE = 40`
 * and OUTRANKS the windows layer's own `z-30` stacking-context boundary. A
 * floating window dragged into the rail band was therefore OCCLUDED BY the rail
 * on mobile but not on desktop — F-1 (docs/mountain-shell-verification.md), the
 * position-dependent, undocumented stacking hazard.
 *
 * This module is the cure AND the inoculation against the NEXT one (F-2): a
 * single ordered scale with one BAND per family, a documented contract for
 * where a new overlay goes, and a token-file ASSERTION (`assertNoSharedBands`,
 * run by zScale.test.ts) that fails the build if two families ever share a band.
 * The next overlay author finds the table + the rule IN this file, not in tribal
 * memory.
 *
 * THE FIVE SHELL FAMILIES (the brief's order — scene < windows < bars < Werner)
 * ----------------------------------------------------------------------------
 * Plus the in-page overlay stack the windows must stay under (modal/ad/toast),
 * already established by components/lemon + components/ad. Each family owns a
 * contiguous, NON-OVERLAPPING band; the constant inside a band is the value a
 * member renders at. The ORDER is the law (lower paints under higher); the exact
 * numbers are spaced with headroom so a family can grow without colliding.
 *
 *   ┌── band ──┬── range ──┬─────────────────────────────────────────────────┐
 *   │ scene    │   0– 9    │ the living mountainscape <Scene/> (z-0) + the     │
 *   │          │           │ operator SceneStatusBadge that floats within it.  │
 *   │ windows  │  20–39    │ the WindowsLayer + every WorkspaceWindow. A window│
 *   │          │           │ paints OVER the scene, UNDER the bars — so the    │
 *   │          │           │ nav rail is always reachable even with a window   │
 *   │          │           │ dragged into its band (the F-1 fix: windows < bars│
 *   │          │           │ on EVERY tier, not just desktop).                 │
 *   │ bars     │  40–49    │ Topbar + bottom NavRail (incl. its mobile         │
 *   │          │           │ absolute/hamburger states) — chrome that must     │
 *   │          │           │ stay above windows so navigation never hides.     │
 *   │ launcher │  50–59    │ rail-spawned in-place overlays that belong to the │
 *   │          │           │ bar layer but sit just above it: ProductsLauncher,│
 *   │          │           │ CommandPalette, LemonSelect/LemonDropdown menus.  │
 *   │ werner   │  60–69    │ the autonomous PenguinMascot + its ice-fishing    │
 *   │          │           │ cursor layer — a free agent that floats over all  │
 *   │          │           │ chrome (operator's ask), under the modal stack.   │
 *   │ modal    │ 100–119   │ LemonModal (focus-trapped dialogs) — above all    │
 *   │          │           │ shell chrome; windows are guaranteed BELOW this.  │
 *   │ menu-over-modal│120–129│ a menu opened FROM inside a modal (Notebook     │
 *   │          │           │ SlashMenu) — must clear the modal it lives in.    │
 *   │ ad       │ 150–169   │ the always-on Times-Square AdBorder overlay.      │
 *   │ toast    │ 200+      │ LemonToast — the last word, over everything.      │
 *   └──────────┴───────────┴─────────────────────────────────────────────────┘
 *
 * RIGOR: "no two families share a band" is enforced by `assertNoSharedBands()`
 * + zScale.test.ts (an assertion, NOT this comment). Migrating a literal? Use a
 * token below; never re-introduce a bare z-number in shell/ or scene/.
 */

/** A half-open band [min, max) a family's z-values must fall inside. */
export interface ZBand {
  readonly min: number;
  readonly max: number;
}

/**
 * The ordered family bands. Order in this object == paint order (earlier =
 * lower = painted under). Ranges are half-open [min, max). Keep them disjoint;
 * `assertNoSharedBands()` proves it.
 */
export const Z_BANDS = {
  scene: { min: 0, max: 10 },
  windows: { min: 20, max: 40 },
  bars: { min: 40, max: 50 },
  launcher: { min: 50, max: 60 },
  werner: { min: 60, max: 70 },
  modal: { min: 100, max: 120 },
  menuOverModal: { min: 120, max: 130 },
  ad: { min: 150, max: 170 },
  toast: { min: 200, max: 1000 },
} as const satisfies Record<string, ZBand>;

export type ZFamily = keyof typeof Z_BANDS;

/**
 * The concrete z-index a member of each family renders at. These are the values
 * the shell consumes; each sits inside its family's band (proven by the test).
 *
 *   scene             0   — the <Scene/> backdrop (also the SceneStatusBadge).
 *   windowsLayer      20  — the WindowsLayer container's stacking-context floor.
 *   windowBase        21  — WINDOW_Z_BASE: a window = windowBase + its stack z,
 *                            kept inside the windows band by WINDOW_Z_SPAN.
 *   bar               40  — Topbar + bottom NavRail (all tiers).
 *   barFloating       45  — a bar control that must sit above sibling bar chrome
 *                            (the mobile hamburger / collapse toggle).
 *   launcher          50  — ProductsLauncher / CommandPalette / Lemon menus.
 *   werner            60  — the ice-fishing cursor layer (under the mascot).
 *   wernerMascot      61  — the PenguinMascot itself (one above its cursor).
 *   modal             100 — LemonModal.
 *   menuOverModal     120 — a menu opened from inside a modal.
 *   ad                150 — the AdBorder overlay.
 *   toast             200 — LemonToast.
 */
export const zIndex = {
  scene: 0,
  windowsLayer: 20,
  windowBase: 21,
  bar: 40,
  barFloating: 45,
  launcher: 50,
  werner: 60,
  wernerMascot: 61,
  modal: 100,
  menuOverModal: 120,
  ad: 150,
  toast: 200,
} as const;

/**
 * The maximum per-window z OFFSET above `windowBase`. With windowBase = 21 and
 * the windows band ending at 40 (exclusive), a window's rendered z
 * (windowBase + offset) must stay < 40 → offset ≤ 18. We clamp the monotonic
 * window z-counter into this span so a long-lived session that opens/focuses
 * many windows can never climb a window OUT of its band and into the bars.
 * (MAX_WINDOWS = 8 means at most 8 distinct live depths; the span covers far
 * more, but the clamp makes the invariant hold for ANY counter value.)
 */
export const WINDOW_Z_SPAN = Z_BANDS.windows.max - 1 - zIndex.windowBase; // 18

/** Clamp a window's stack offset so windowBase + offset stays in the windows band. */
export function clampWindowOffset(offset: number): number {
  if (!Number.isFinite(offset) || offset < 0) return 0;
  return Math.min(Math.round(offset), WINDOW_Z_SPAN);
}

/** The rendered z-index for a window at stack offset `offset` (clamped into band). */
export function windowZIndex(offset: number): number {
  return zIndex.windowBase + clampWindowOffset(offset);
}

/**
 * ASSERTION (rigor #3) — no two family bands overlap. Throws on violation.
 * Called by zScale.test.ts; also safe to call at module-eval in dev if desired.
 * This is the F-2 guard: a future family added with an overlapping band fails
 * here, loudly, instead of silently re-creating an F-1.
 *
 * `bands` defaults to the shipped `Z_BANDS` (the production call). The parameter
 * exists so the test can feed an overlapping band set to the SAME shipped
 * function and prove it bites — no re-implemented copy of the check.
 */
export function assertNoSharedBands(bands: Record<string, ZBand> = Z_BANDS): void {
  const entries = Object.entries(bands);
  // Bands must be individually well-formed (min < max).
  for (const [name, band] of entries) {
    if (!(band.min < band.max)) {
      throw new Error(`zScale: band "${name}" is malformed (min ${band.min} !< max ${band.max}).`);
    }
  }
  // Sorted by min, each band must start at or after the previous band's max
  // (half-open ranges → touching is fine, overlapping is not).
  const sorted = [...entries].sort((a, b) => a[1].min - b[1].min);
  for (let i = 1; i < sorted.length; i++) {
    const [prevName, prev] = sorted[i - 1];
    const [name, band] = sorted[i];
    if (band.min < prev.max) {
      throw new Error(
        `zScale: bands "${prevName}" [${prev.min},${prev.max}) and "${name}" ` +
          `[${band.min},${band.max}) overlap — every family must own a disjoint band (F-1/F-2 guard).`,
      );
    }
  }
}

/** Assert a concrete z-value falls inside its declared family band. */
export function assertInBand(family: ZFamily, value: number): void {
  const band = Z_BANDS[family];
  if (value < band.min || value >= band.max) {
    throw new Error(
      `zScale: ${family} z-value ${value} is outside its band [${band.min},${band.max}).`,
    );
  }
}
