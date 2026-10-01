/**
 * documentSpace.ts — pure mappings between the route, the mothership, and
 * the tab tree, so the strip and its tests share one derivation.
 *
 *   - mothershipForPath: which tree the current route files under.
 *   - rootRefForPath: the surface the current route IS, as a root-tab ref.
 *   - routeForTab: the canonical URL a tab ACTIVATES to (null = the kind has
 *     no canonical route: the strip renders the honest "opens as window"
 *     bridge, never a guessed embedding; a Write section scopes in place).
 *   - routeTabFor: the tab whose route an activation navigates to — the tab
 *     itself, or, for a Write section (which scopes its piece in place), the
 *     piece it belongs to (critic P-B).
 *   - adoptTabForRoute: what the route → tree sync does on a route change.
 *     An open tab that already shows the route is ADOPTED before any root is
 *     seeded, so a child tab stays a child (forensic defect 2); a navigation
 *     that carries a branch intent files its surface under the tab it was
 *     triggered from (critic P-D).
 *   - findOpenTab / findClosedTab: a tab by its fields (side, kind, ref,
 *     parent) in its tree. tab_ids are opaque (tabId.ts): nothing here or
 *     in any caller builds or parses one.
 */
import type { BranchIntent } from "./branchNavigation";
import { mothershipForPath } from "./mothershipForPath";
import { sectionIdFromRef } from "./sectionRef";
import {
  pathTo,
  subtreeIds,
  type BranchOrigin,
  type TabKind,
  type TabNode,
  type TabSide,
  type TabTree,
} from "./tabTree";

export { mothershipForPath };

export { rootRefForPath, type RootRef } from "./routeRef";
import { rootRefForPath, segment, type RootRef } from "./routeRef";

/** The route path (no query) a tab's surface lives at, or null. */
function basePathForTab(tab: TabNode): string | null {
  switch (tab.kind) {
    case "reader":
      return `/read/${encodeURIComponent(tab.ref)}`;
    case "research":
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

function isSectionTab(tab: TabNode): boolean {
  return tab.kind === "document" && sectionIdFromRef(tab.ref) !== null;
}

/**
 * The tab whose canonical route shows `tabId`: the tab itself when it has a
 * route; for a Write section, the nearest ancestor that has one (its piece),
 * since a section is a view of that piece; otherwise null (the honest
 * "opens as window" bridge).
 */
export function routeTabFor(tree: TabTree, tabId: string): TabNode | null {
  const tab = tree.nodes[tabId];
  if (!tab) return null;
  if (basePathForTab(tab) !== null) return tab;
  if (!isSectionTab(tab)) return null;
  const ancestry = pathTo(tree, tabId);
  for (let i = ancestry.length - 2; i >= 0; i--) {
    const up = tree.nodes[ancestry[i]];
    if (basePathForTab(up) !== null) return up;
  }
  return null;
}

/** Does this tab show the surface at `pathname`? Compared decoded, so
 *  `/read/a%20b` and `/read/a b` are one surface. */
export function tabShowsPath(tab: TabNode, pathname: string): boolean {
  const base = basePathForTab(tab);
  return base !== null && segment(base) === segment(pathname);
}

/** What identifies a tab's view, for finding it: its tree (the mothership),
 *  pane side, kind, ref and parent. A tab_id is opaque (tabId.ts) and is
 *  never parsed for any of these. */
export interface TabFields {
  side?: TabSide;
  kind: TabKind;
  ref: string;
  parent_tab_id: string | null;
}

function matches(tree: TabTree, node: TabNode, q: TabFields): boolean {
  return (
    node.mothership === tree.mothership &&
    node.side === (q.side ?? "left") &&
    node.kind === q.kind &&
    node.ref === q.ref &&
    node.parent_tab_id === q.parent_tab_id
  );
}

/** The open tab showing `q` under `q.parent_tab_id` (null = a root), or
 *  null. Duplicate-open, re-attach and the cross-pane seam find a tab here. */
export function findOpenTab(tree: TabTree, q: TabFields): string | null {
  const siblings =
    q.parent_tab_id === null
      ? tree.root_order
      : Object.hasOwn(tree.nodes, q.parent_tab_id)
        ? tree.nodes[q.parent_tab_id].child_order
        : [];
  return siblings.find((id) => Object.hasOwn(tree.nodes, id) && matches(tree, tree.nodes[id], q)) ?? null;
}

/** A retired tab that showed `q` under that parent when it closed, or null. */
export function findClosedTab(tree: TabTree, q: TabFields): string | null {
  return Object.keys(tree.history).find((id) => matches(tree, tree.history[id].node, q)) ?? null;
}

export type RouteAdoption =
  | { action: "none" }
  | { action: "activate"; tabId: string }
  | { action: "seed"; ref: RootRef }
  | { action: "branch"; parentId: string; ref: RootRef; origin: BranchIntent["origin"] };

/** The branch_origin a branch intent gives its new tab. */
export function branchOriginOf(origin: BranchIntent["origin"]): BranchOrigin {
  return {
    document_id: origin.document_id,
    kind: origin.kind,
    ...(origin.page_index !== undefined
      ? { anchor: { document_id: origin.document_id, page_index: origin.page_index } }
      : {}),
  };
}

/**
 * What the route → tree sync does when the route is `pathname`:
 *
 *   1. not a document surface: nothing;
 *   2. a branch intent whose parent is open in this tree: the parent's open
 *      child showing the route is activated (or the parent itself, when it
 *      shows it), else a CHILD is spawned under the parent — the surface was
 *      triggered from that tab's document;
 *   3. the active tab already shows it: nothing;
 *   4. the active tab has no route of its own (a Write section scoped in
 *      place) and an ancestor shows it: nothing — the section is the view;
 *   5. an open tab shows it: ADOPT it — the nearest ancestor of the active
 *      tab first (Back from a child lands on its parent), else the first in
 *      depth-first order;
 *   6. otherwise seed a root tab for it.
 *
 * Step 5 before step 6 is the whole of forensic defect 2: a child reader tab
 * whose activation navigated here is found, so no root is minted beside it.
 * Step 2 is critic P-D: a deep research spun from a reader, or a link out of
 * it, is a branch of the reader's tab, never a root in another tree.
 */
export function adoptTabForRoute(
  tree: TabTree,
  pathname: string,
  intent?: BranchIntent | null,
): RouteAdoption {
  const ref = rootRefForPath(pathname);
  if (!ref) return { action: "none" };
  if (intent && intent.mothership === tree.mothership && Object.hasOwn(tree.nodes, intent.parentTabId)) {
    const parent = tree.nodes[intent.parentTabId];
    if (tabShowsPath(parent, pathname)) {
      return tree.active_tab_id === parent.tab_id ? { action: "none" } : { action: "activate", tabId: parent.tab_id };
    }
    const open = parent.child_order.find(
      (id) => Object.hasOwn(tree.nodes, id) && tabShowsPath(tree.nodes[id], pathname),
    );
    if (open) {
      return tree.active_tab_id === open ? { action: "none" } : { action: "activate", tabId: open };
    }
    return { action: "branch", parentId: parent.tab_id, ref, origin: intent.origin };
  }
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
