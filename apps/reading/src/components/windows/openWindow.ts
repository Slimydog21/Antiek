import { lazy } from "react";
import type { ComponentType, LazyExoticComponent } from "react";

import { useWindows } from "../../workspace/windowsStore";
import type { OpenWindowOptions } from "../../workspace/windowsStore";

/**
 * openWindow — the spawn API for workspace windows (SPR-09 M5; INVERTED SPR-04).
 *
 * A `WindowKind` is a route-ish key identifying which product PAGE a window
 * hosts. The registry maps each kind to the real page component; the host
 * layer (WindowsLayer) reads windowsStore + this registry to render each
 * window's page inside a <WorkspaceWindow>.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * WINDOWS-VS-NAVIGATE POLICY — INVERTED in AMS2 SPR-04 (the windows-default
 * keystone). The old SPR-09 policy made navigate the default and a window the
 * additive "open in window" (⊞) affordance; v1 shipped that and the operator
 * complaint #2 was "windows were manual, not the default" — they never saw a
 * window because the default click always navigated full-page. SPR-04 inverts
 * the default for CONTRACT-VERIFIED (within-contract) surfaces.
 * ─────────────────────────────────────────────────────────────────────────
 *
 *   WINDOW IS THE DEFAULT for a within-contract surface — a page that satisfies
 *   the window-adaptation contract (drops its opaque bg + fills its container,
 *   owns no internal dock, does not need the full viewport) OR a window-native
 *   page like `subaction`. The default (primary) click on a within-contract
 *   product/asset opens a transparent, ad-bordered window over the scene. No
 *   separate ⊞ button is needed for these — the window IS the click.
 *     - a product activation (Research / Read / Write / Speak from the
 *       launcher) opens a `subaction` window listing that workflow's
 *       sub-actions over the scene (M1),
 *     - a within-contract reference surface (Stats, the Library shelf, a
 *       document, an outcome) opens as a floating window alongside the page
 *       that spawned it (M2).
 *
 *   NAVIGATE FULL-PAGE stays the default for:
 *     - the NavRail's four PRIMARY workflow switches (Research ↔ Read ↔ Write
 *       ↔ Speak) — these are destinations, not floats (NavRail is untouched),
 *     - OUT-OF-CONTRACT surfaces — a page that assumes the full viewport or
 *       owns its own dock/floating-panel system. These are NOT in WINDOW_PAGES
 *       and must never be given a third adaptation to force them to float:
 *         · ResearchWorkstation — the chat-first IDE owns a PanelHost dock
 *           (docked sidebar + bottom chat) and the active /inv/:id view is
 *           classified dense-opaque-keep (its body text must not ride over the
 *           moving scene); nesting a dock-owning page in a window is
 *           out-of-contract. → navigate.
 *         · WrestleApp — the PDF wrestler assumes the full viewport for its
 *           reading/region-selection surface. → navigate.
 *       (See the page-by-page classification in windows/README.md.)
 *     - a deep/operator surface from the launcher that is a context switch,
 *       not a companion (Operator console, Trust, Settings, governance…).
 *
 * The legacy additive ⊞ "open in window" affordance is retained for
 * window-eligible run/settings rows (a power affordance), but for a product
 * activation the window is now the DEFAULT, not a secondary button.
 */

export type WindowPageRenderer =
  | ComponentType<Record<string, unknown>>
  | LazyExoticComponent<ComponentType<Record<string, unknown>>>;

/**
 * Window-hostable pages. Two flavours live here, both contract-safe to float:
 *
 *   1. CONTRACT-VERIFIED route pages — pages that ALSO have a full-page route
 *      and satisfy the (a)+(b) window-adaptation contract (drop opaque bg +
 *      fill container, no internal dock). Stats + Library carry the two-line
 *      `useInWindow()` diff (SPR-09 M4); more can be added as they are verified
 *      contract-safe. These are mapped from routes via ROUTE_TO_KIND below.
 *
 *   2. WINDOW-NATIVE pages — purpose-built to render ONLY in a window, so they
 *      are authored glass-native and need no (a)+(b) route contract. `subaction`
 *      (SPR-04 M1, the SubActionList) is the first: it lists a workflow's
 *      sub-actions and only ever appears as a product-activation window. It has
 *      NO route, so it is deliberately absent from ROUTE_TO_KIND.
 *
 * NOT here (deliberately, per the policy above): ResearchWorkstation and
 * WrestleApp — they own their own dock/floating panel systems and assume the
 * full viewport, so hosting them inside a window is out-of-contract. They stay
 * full-page routes and the default click NAVIGATES (never given a 3rd edit).
 */
export const WINDOW_PAGES: Record<string, { title: string; renderer: WindowPageRenderer }> = {
  stats: {
    title: "Substrate stats",
    renderer: lazy(() => import("../../modes/Stats")),
  },
  library: {
    title: "Library",
    renderer: lazy(() => import("../../modes/Library")),
  },
  // SPR-04 M1 — the sub-action window. Window-native (no full-page route),
  // hosted when a product is activated from the launcher. Reads { workflow }
  // from its payload and lists that workflow's MODE_TAXONOMY entries.
  subaction: {
    title: "Sub-actions",
    renderer: lazy(() => import("./SubActionList")),
  },
  // A document identity opens the SAME rights-aware HTML reader used by
  // `/read/:documentId`. The payload contains no caller-supplied HTML; the
  // reader remains the sole owner of fetching and servability truth.
  reader: {
    title: "Source reader",
    renderer: lazy(() => import("../../modes/Reading")),
  },
};

export type WindowEligibleKind = keyof typeof WINDOW_PAGES;

/** Is this kind hostable in a window (i.e. contract-verified)? */
export function isWindowEligible(kind: string): kind is WindowEligibleKind {
  return Object.prototype.hasOwnProperty.call(WINDOW_PAGES, kind);
}

/**
 * Map a route path (as the launcher/taxonomy knows it) to a window-eligible
 * kind, or null if that route is not contract-verified for windows. Keeps the
 * launcher decoupled from the kind vocabulary — it only knows routes.
 */
const ROUTE_TO_KIND: Record<string, WindowEligibleKind> = {
  "/stats": "stats",
  "/library": "library",
};

export function windowKindForRoute(route: string | undefined): WindowEligibleKind | null {
  if (!route) return null;
  return ROUTE_TO_KIND[route] ?? null;
}

/**
 * Spawn a workspace window hosting `kind`. Returns the window id (existing id
 * if one for this kind/instance is already open — re-opening focuses).
 *
 * Uses a stable per-kind id by default so the same surface doesn't stack
 * (one Stats window, one Library window). Pass `opts.id` for per-instance
 * windows (e.g. one window per documentId).
 */
export function openWindow(
  kind: WindowEligibleKind,
  payload: Record<string, unknown> = {},
  opts: OpenWindowOptions = {},
): string {
  const page = WINDOW_PAGES[kind];
  return useWindows.getState().open(kind, payload, {
    title: page?.title ?? kind,
    id: opts.id ?? `win:${kind}`,
    ...opts,
  });
}
