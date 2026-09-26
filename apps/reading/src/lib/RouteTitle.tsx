/**
 * RouteTitle — name the page in the browser tab (FFX SPR-01 M4, closes A-13).
 *
 * The auth crawl read document.title === "Antiek — reading" on 369/369
 * visits: every tab, history entry and bookmark said the same thing. The
 * shell already owns the product's names for its pages — MODE_TAXONOMY in
 * shell/workflowTaxonomy.ts (lane A's file; imported, never edited here) —
 * so the title is derived from it: "<Mode name> · Antiek", or "Antiek" when
 * nothing matches.
 *
 * The same lookup names breadcrumbs (components/navigation/Breadcrumbs.tsx),
 * so a tab title and the crumb for the same page can never disagree.
 *
 * Matching, in order:
 *   1. exact static route ("/notebooks"). When two modes share one route and
 *      it is a workflow's door ("/write": Block repository + Write editor;
 *      "/speak": Speak + Interviews), the WORKFLOW's name wins ("Write").
 *   2. parameterised pattern ("/read/:documentId"), most static segments
 *      first, so "/speak/invite/:token" beats "/speak/:projectId".
 *   3. the longest routed parent ("/write/dlv-…" → "/write" → "Write"), for
 *      child routes App.tsx mounts but the taxonomy does not list.
 *
 * Popout windows (/_panel/:panelId) are skipped: PanelWindowApp sets its own
 * "antiek · popout · <panel>" title and must not be fought.
 */
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { MODE_TAXONOMY, WORKFLOWS, type ModeEntry } from "../shell/workflowTaxonomy";

export const TITLE_SUFFIX = "Antiek";

export interface RouteMatch {
  /** The product's name for the page. */
  name: string;
  /** The taxonomy route that matched (a pattern for parameterised routes). */
  route: string;
  /** Param values by name, for a pattern match ("documentId" → "doc-1"). */
  params: Record<string, string>;
  /** How it matched; "parent" means a routed ancestor named it. */
  via: "exact" | "pattern" | "parent";
}

function normalize(pathname: string): string {
  const path = (pathname || "/").split(/[?#]/)[0];
  return path.length > 1 ? path.replace(/\/+$/, "") || "/" : "/";
}

function segmentsOf(path: string): string[] {
  return path.split("/").filter(Boolean);
}

const ROUTED: readonly ModeEntry[] = MODE_TAXONOMY.filter(
  (m): m is ModeEntry & { route: string } => Boolean(m.route),
);

/** The workflow whose door is `route`, if any ("/write" → Write). */
function workflowDoorName(route: string): string | null {
  for (const wf of Object.values(WORKFLOWS)) {
    if (wf.defaultRoute === route) return wf.label;
  }
  return null;
}

function exactName(path: string): string | null {
  const hits = ROUTED.filter((m) => m.route === path);
  if (hits.length === 0) return null;
  if (hits.length > 1) return workflowDoorName(path) ?? hits[0].label;
  return hits[0].label;
}

interface Pattern {
  entry: ModeEntry;
  route: string;
  parts: string[];
  staticCount: number;
}

const PATTERNS: readonly Pattern[] = ROUTED.filter((m) => m.route!.includes("/:"))
  .map((entry) => {
    const parts = segmentsOf(entry.route!);
    return { entry, route: entry.route!, parts, staticCount: parts.filter((p) => !p.startsWith(":")).length };
  })
  // Most specific first: more static segments win.
  .sort((a, b) => b.staticCount - a.staticCount);

function patternMatch(path: string): RouteMatch | null {
  const segs = segmentsOf(path);
  for (const p of PATTERNS) {
    if (p.parts.length !== segs.length) continue;
    const params: Record<string, string> = {};
    const ok = p.parts.every((part, i) => {
      if (part.startsWith(":")) {
        params[part.slice(1)] = segs[i];
        return true;
      }
      return part === segs[i];
    });
    if (ok) return { name: p.entry.label, route: p.route, params, via: "pattern" };
  }
  return null;
}

/**
 * Exact or pattern match only (no parent fallback). Breadcrumbs use this per
 * path prefix; titles use {@link matchRoute}.
 */
export function matchRouteExactly(pathname: string): RouteMatch | null {
  const path = normalize(pathname);
  const exact = exactName(path);
  if (exact) return { name: exact, route: path, params: {}, via: "exact" };
  return patternMatch(path);
}

/** Resolve a pathname to the product's name for the page, or null. */
export function matchRoute(pathname: string): RouteMatch | null {
  const path = normalize(pathname);
  const direct = matchRouteExactly(path);
  if (direct) return direct;
  const segs = segmentsOf(path);
  // Longest routed parent, never the root: "/" naming every unknown path
  // would make /unknown read "Research workstation".
  for (let n = segs.length - 1; n >= 1; n--) {
    const parent = "/" + segs.slice(0, n).join("/");
    const hit = matchRouteExactly(parent);
    if (hit) return { ...hit, via: "parent" };
  }
  return null;
}

export function routeNameFor(pathname: string): string | null {
  return matchRoute(pathname)?.name ?? null;
}

export function titleFor(pathname: string): string {
  const name = routeNameFor(pathname);
  return name ? `${name} · ${TITLE_SUFFIX}` : TITLE_SUFFIX;
}

function isPopout(pathname: string): boolean {
  return pathname === "/_panel" || pathname.startsWith("/_panel/");
}

/** Mount once inside the router. Renders nothing. */
export function RouteTitle(): null {
  const { pathname } = useLocation();
  useEffect(() => {
    if (isPopout(pathname)) return;
    document.title = titleFor(pathname);
  }, [pathname]);
  return null;
}

export default RouteTitle;
