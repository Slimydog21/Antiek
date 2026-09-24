/**
 * documentSpace.ts — pure mappings between the route, the mothership, and
 * the tab tree, so the strip and its tests share one derivation.
 *
 *   - mothershipForPath: which tree the current route files under.
 *   - rootRefForPath: the surface the current route IS, as a root-tab ref.
 *   - routeForTab: the canonical URL a tab ACTIVATES to (null = the kind has
 *     no canonical route — the strip renders the honest "opens as window"
 *     bridge, never a guessed embedding).
 *   - threadForPath: the active tab's ancestry as a Thread, in the ONE form
 *     the Opus Trail lawfully renders (every hop on the SAME canonical
 *     entity — its one-entity integrity contract is not bent).
 */
import type { Thread, ThreadHop } from "../shell/threadModel";
import type { Workflow } from "../shell/workflowTaxonomy";
import { pathTo, type Mothership, type TabKind, type TabNode, type TabTree } from "./tabTree";

export function mothershipForPath(pathname: string): Mothership {
  if (pathname.startsWith("/read") || pathname.startsWith("/library")) return "reading";
  if (pathname.startsWith("/write")) return "writing";
  return "research";
}

const WORKFLOW_OF: Record<Mothership, Exclude<Workflow, "shared">> = {
  research: "research",
  writing: "write",
  reading: "read",
};

export function workflowForMothership(m: Mothership): Exclude<Workflow, "shared"> {
  return WORKFLOW_OF[m];
}

export interface RootRef {
  kind: TabKind;
  ref: string;
  title: string;
}

/** The surface the current route IS, as a root tab reference (null when the
 *  route is not a document-space surface worth a tab — e.g. /home). */
export function rootRefForPath(pathname: string): RootRef | null {
  const read = pathname.match(/^\/read\/(.+)$/);
  if (read) {
    const id = decodeURIComponent(read[1]);
    return { kind: "reader", ref: id, title: id };
  }
  const inv = pathname.match(/^\/inv\/(.+)$/);
  if (inv) {
    const id = decodeURIComponent(inv[1]);
    return { kind: "research", ref: `/inv/${id}`, title: id };
  }
  const write = pathname.match(/^\/write\/(.+)$/);
  if (write) {
    const id = decodeURIComponent(write[1]);
    return { kind: "document", ref: `/write/${id}`, title: id };
  }
  return null;
}

/** The canonical URL activating a tab navigates to, or null when the kind
 *  has none (the honest bridge case). */
export function routeForTab(tab: TabNode): string | null {
  switch (tab.kind) {
    case "reader":
      return `/read/${encodeURIComponent(tab.ref)}`;
    case "research":
    case "thread":
      return tab.ref.startsWith("/") ? tab.ref : `/inv/${encodeURIComponent(tab.ref)}`;
    case "document":
      return tab.ref.startsWith("/") ? tab.ref : null;
    case "companion":
    case "flags":
      return null;
    default:
      return null;
  }
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

/**
 * The active tab's ancestry as a Thread for the Opus Trail. Trail's
 * integrity contract: every hop carries the SAME entity id (a forked id
 * suppresses navigation). The path's canonical entity is the ROOT tab's ref
 * — every descendant is a branch of that one surface, so the contract
 * holds lawfully. Hop kinds narrate the branch: the root is its tab kind,
 * each descendant is its branch_origin kind (footnote / reference /
 * citation / island / research / manual) when it has one.
 */
export function threadForPath(tree: TabTree, activeTabId: string | null): Thread | null {
  if (!activeTabId) return null;
  const path = pathTo(tree, activeTabId);
  if (path.length === 0) return null;
  const root = tree.nodes[path[0]];
  const workflow = workflowForMothership(tree.mothership);
  const hops: ThreadHop[] = path.map((tabId) => {
    const tab = tree.nodes[tabId];
    return {
      workflow,
      entityId: root.ref,
      entityKind: tab.branch_origin?.kind ?? tab.kind,
      seamEventId: null,
      seamActionType: null,
      // The hop's jump target: the tab id it activates.
      provenanceRef: tabId,
      built: true,
      viaProvisionalSeam: false,
    };
  });
  return {
    canonicalEntityId: root.ref,
    canonicalEntityKind: root.kind,
    hops,
    stubs: [],
    isDegenerate: hops.length <= 1,
  };
}
