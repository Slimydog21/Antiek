import type { Mothership } from "./tabTree";

/**
 * Which tab tree the current route files under. Kept apart from
 * documentSpace (which pulls the tab-tree model) so the keyboard dispatcher
 * and the right-pane switch, both in the entry chunk, can ask it without
 * loading the model; documentSpace re-exports it unchanged.
 */
export function mothershipForPath(pathname: string): Mothership {
  if (pathname.startsWith("/read") || pathname.startsWith("/library")) return "reading";
  if (pathname.startsWith("/write")) return "writing";
  return "research";
}
