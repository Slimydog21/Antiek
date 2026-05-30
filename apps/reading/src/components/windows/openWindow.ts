import { lazy } from "react";
import type { ComponentType, LazyExoticComponent } from "react";

import { useWindows } from "../../workspace/windowsStore";
import type { OpenWindowOptions } from "../../workspace/windowsStore";

/**
 * openWindow — the spawn API for workspace windows (SPR-09 M5).
 *
 * A `WindowKind` is a route-ish key identifying which product PAGE a window
 * hosts. The registry maps each kind to the real page component; the host
 * layer (WindowsLayer) reads windowsStore + this registry to render each
 * window's page inside a <WorkspaceWindow>.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * WINDOWS-VS-NAVIGATE POLICY (SPR-09 M5, rigor #2 — steelman of full-page)
 * ─────────────────────────────────────────────────────────────────────────
 * Full-page navigation stays the DEFAULT and is correct for most actions:
 * it is simpler, needs zero adaptation, and matches a single focused task.
 * A window is justified ONLY when the operator's "multiple terminals" vision
 * applies — i.e. they want this surface ALONGSIDE another, floating over the
 * scene, not instead of it.
 *
 *   OPEN A WINDOW when:
 *     - the operator explicitly asks for a floating/secondary view
 *       ("open in window", asset/citation click that should not leave the
 *       current page, a side investigation kicked off mid-task),
 *     - the surface is reference-like and benefits from coexisting with the
 *       page that spawned it (Stats, Library shelf, a document, an outcome).
 *
 *   NAVIGATE FULL-PAGE when:
 *     - it is a primary workflow switch (Research ↔ Read ↔ Write ↔ Speak via
 *       the NavRail) — these are destinations, not floats,
 *     - the surface assumes the full viewport or owns its own dock/floating
 *       panel system (the ResearchWorkstation IDE, the PDF wrestler) — nesting
 *       a dock-owning page inside a window is out-of-contract,
 *     - a deep/operator surface from the launcher that is a context switch,
 *       not a companion.
 *
 * The ProductsLauncher keeps `navigate()` for its primary entries; it gains an
 * additive "open in window" affordance for the window-eligible kinds below.
 */

export type WindowPageRenderer =
  | ComponentType<Record<string, unknown>>
  | LazyExoticComponent<ComponentType<Record<string, unknown>>>;

/**
 * Window-eligible pages. ONLY pages that satisfy the window-adaptation
 * contract (drop opaque bg + fill container, no internal dock system) belong
 * here. Stats + Library are adapted in SPR-09 M4; more can be added as they
 * are verified contract-safe.
 *
 * NOT here (deliberately, per the policy above): ResearchWorkstation and
 * WrestleApp — they own their own dock/floating panel systems and assume the
 * full viewport, so hosting them inside a window is out-of-contract. They stay
 * full-page routes.
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
