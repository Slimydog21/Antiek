/**
 * documentSpace.ts — pure mappings between the route, the mothership, and
 * the tab tree, so the strip and its tests share one derivation.
 *
 *   - mothershipForPath: which tree the current route files under.
 *   - rootRefForPath: the surface the current route IS, as a root-tab ref.
 *   - routeForTab: the canonical URL a tab ACTIVATES to (null = the kind has
 *     no canonical route — the strip renders the honest "opens as window"
 *     bridge, never a guessed embedding).
 *   - adoptTabForRoute: what the route → tree sync does on a route change.
 *     An open tab that already shows the route is ADOPTED before any root is
 *     seeded, so a child tab stays a child (forensic defect 2).
 */
import { mothershipForPath } from "./mothershipForPath";
import { pathTo, subtreeIds, type TabKind, type TabNode, type TabTree } from "./tabTree";

export { mothershipForPath };

export interface RootRef {
  kind: TabKind;
  ref: string;
}

/** First path segments under /read that are app surfaces, not documents
 *  (App.tsx: /read/meta-reading and /read/meta-reading/:assetId). */
const READ_SURFACES = new Set(["meta-reading"]);

function segment(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

/** The surface the current route IS, as a root tab reference (null when the
 *  route is not a document-space surface worth a tab — e.g. /home, or the
 *  meta-reading generator that lives under /read). */
export function rootRefForPath(pathname: string): RootRef | null {
  const read = pathname.match(/^\/read\/([^/]+)\/?$/);
  if (read) {
    const id = segment(read[1]);
    return READ_SURFACES.has(id) ? null : { kind: "reader", ref: id };
  }
  const inv = pathname.match(/^\/inv\/([^/]+)\/?$/);
  if (inv) return { kind: "research", ref: `/inv/${segment(inv[1])}` };
  const write = pathname.match(/^\/write\/([^/]+)\/?$/);
  if (write) return { kind: "document", ref: `/write/${segment(write[1])}` };
  return null;
}

/** The route path (no query) a tab's surface lives at, or null. */
function basePathForTab(tab: TabNode): string | null {
  switch (tab.kind) {
    case "reader":
      return `/read/${encodeURIComponent(tab.ref)}`;
    case "research":
    case "thread":
      return tab.ref.startsWith("/") ? tab.ref : `/inv/${encodeURIComponent(tab.ref)}`;
    case "document":
      return tab.ref.startsWith("/") ? tab.ref : null;
    default:
      return null;
  }
}

/** The canonical URL activating a tab navigates to, or null when the kind
 *  has none (the honest bridge case). A tab whose route belongs to another
 *  mode carries `?m=<its tree>`, so opening it never switches trees. */
export function routeForTab(tab: TabNode): string | null {
  const base = basePathForTab(tab);
  if (base === null) return null;
  return mothershipForPath(base) === tab.mothership ? base : `${base}?m=${tab.mothership}`;
}

/** Does this tab show the surface at `pathname`? Compared decoded, so
 *  `/read/a%20b` and `/read/a b` are one surface. */
export function tabShowsPath(tab: TabNode, pathname: string): boolean {
  const base = basePathForTab(tab);
  return base !== null && segment(base) === segment(pathname);
}

/** Stable root tab id for a surface ref. */
export function rootTabId(ref: RootRef): string {
  return `root:${ref.kind}:${ref.ref}`;
}

/** Stable child tab id under a parent (unique per parent, so the same
 *  surface can lawfully branch off two parents — tabs are navigation state,
 *  not provenance). */
export function childTabId(parentTabId: string, kind: TabKind, ref: string): string {
  return `child:${parentTabId}:${kind}:${ref}`;
}

/** `base` when no tab (open or closed) holds it, else `base~2`, `base~3`…
 *  A closed tab keeps its id in history (its numbers stay retired and its
 *  undo stays valid), so reopening the same surface takes a fresh id. */
export function freshTabId(tree: TabTree, base: string): string {
  const known = (id: string) => Object.hasOwn(tree.nodes, id) || Object.hasOwn(tree.history, id);
  if (!known(base)) return base;
  let n = 2;
  while (known(`${base}~${n}`)) n++;
  return `${base}~${n}`;
}

export type RouteAdoption =
  | { action: "none" }
  | { action: "activate"; tabId: string }
  | { action: "seed"; ref: RootRef };

/**
 * What the route → tree sync does when the route is `pathname`:
 *
 *   1. not a document surface: nothing;
 *   2. the active tab already shows it: nothing;
 *   3. the active tab has no route of its own (a Write section scoped in
 *      place) and an ancestor shows it: nothing — the section is the view;
 *   4. an open tab shows it: ADOPT it — the nearest ancestor of the active
 *      tab first (Back from a child lands on its parent), else the first in
 *      depth-first order;
 *   5. otherwise seed a root tab for it.
 *
 * Step 4 before step 5 is the whole of forensic defect 2: a child reader tab
 * whose activation navigated here is found, so no root is minted beside it.
 */
export function adoptTabForRoute(tree: TabTree, pathname: string): RouteAdoption {
  const ref = rootRefForPath(pathname);
  if (!ref) return { action: "none" };
  const active = tree.active_tab_id ? tree.nodes[tree.active_tab_id] : undefined;
  const ancestry = active ? pathTo(tree, active.tab_id) : [];
  if (active && tabShowsPath(active, pathname)) return { action: "none" };
  if (active && basePathForTab(active) === null) {
    if (ancestry.some((id) => tabShowsPath(tree.nodes[id], pathname))) return { action: "none" };
  }
  for (let i = ancestry.length - 2; i >= 0; i--) {
    if (tabShowsPath(tree.nodes[ancestry[i]], pathname)) return { action: "activate", tabId: ancestry[i] };
  }
  for (const rootId of tree.root_order) {
    for (const id of subtreeIds(tree, rootId)) {
      if (tabShowsPath(tree.nodes[id], pathname)) return { action: "activate", tabId: id };
    }
  }
  return { action: "seed", ref };
}
