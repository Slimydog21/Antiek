/**
 * branchNavigation.ts — "tabs for all the links, footnotes, documents
 * triggered from a single document, or deep researches triggered from a
 * single document" (the operator's cockpit prompt; critic P-D).
 *
 * A surface that opens something FROM the document on screen (a deep
 * research spun from a highlight, a link to another document, a Write
 * citation traced to its source) navigates with a branch intent instead of a
 * bare path. The route → tree sync (documentSpace.adoptTabForRoute) reads the
 * intent from the history entry's state and files the new surface as a CHILD
 * of the tab it was triggered from, in that tab's tree, instead of seeding a
 * root in whichever tree the new route would otherwise pick.
 *
 * Callers navigate through useBranchTo, which loads this module on the first
 * branch (the reader is in the entry chunk; this is not). The parent comes
 * from tabTreeHandle, which the tab-tree store fills when it loads; before
 * that there is no tree to branch from and the navigation is a plain one —
 * an honest root later, never a guessed parent.
 */
import type { NavigateOptions } from "react-router-dom";

import { mothershipForPath } from "./mothershipForPath";
import type { BranchKind, Mothership } from "./tabTree";
import { tabTreeHandle } from "./tabTreeHandle";

/** Where the branch was triggered from, as the new tab's branch_origin. */
export interface BranchSource {
  /** The document the branch was taken from. */
  document_id: string;
  kind: BranchKind;
  /** The reader page it was taken on, when there is one. */
  page_index?: number;
}

/** What a branching navigation carries in its history-entry state. */
export interface BranchIntent {
  parentTabId: string;
  mothership: Mothership;
  origin: BranchSource;
}

/** The history-state key the intent rides under. */
export const BRANCH_STATE_KEY = "tabBranch";

/** The intent a location's state carries, or null. Tolerant of any state
 *  shape: other surfaces put their own things in history state. */
export function branchIntentOf(state: unknown): BranchIntent | null {
  if (!state || typeof state !== "object") return null;
  const raw = (state as Record<string, unknown>)[BRANCH_STATE_KEY];
  if (!raw || typeof raw !== "object") return null;
  const b = raw as Partial<BranchIntent>;
  if (typeof b.parentTabId !== "string" || typeof b.mothership !== "string") return null;
  if (!b.origin || typeof b.origin.document_id !== "string" || typeof b.origin.kind !== "string") return null;
  return b as BranchIntent;
}

/** `path` with `?m=<mothership>` added when its route belongs to another
 *  tree, so the branch stays in the tree it was taken from. */
function inTree(path: string, mothership: Mothership): string {
  const [pathname, query = ""] = path.split("?", 2);
  if (mothershipForPath(pathname, query ? `?${query}` : "") === mothership) return path;
  const params = new URLSearchParams(query);
  params.set("m", mothership);
  return `${pathname}?${params.toString()}`;
}

/**
 * The navigation for opening `to` as a branch of the tab on screen at
 * `from`. Without a loaded tree (or an active tab) it is `{ to }` unchanged.
 */
export function branchNavigation(
  to: string,
  from: { pathname: string; search: string },
  origin: BranchSource,
): { to: string; options?: NavigateOptions } {
  const mothership = mothershipForPath(from.pathname, from.search);
  const parentTabId = tabTreeHandle.store?.getState().trees[mothership]?.active_tab_id ?? null;
  if (!parentTabId) return { to };
  const intent: BranchIntent = { parentTabId, mothership, origin };
  return { to: inTree(to, mothership), options: { state: { [BRANCH_STATE_KEY]: intent } } };
}
