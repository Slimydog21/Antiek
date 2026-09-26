import type { Mothership } from "./tabTree";

/**
 * Which tab tree the current route files under. Kept apart from
 * documentSpace (which pulls the tab-tree model) so the keyboard dispatcher
 * and the right-pane switch, both in the entry chunk, can ask it without
 * loading the model; documentSpace re-exports it unchanged.
 *
 * `?m=<mothership>` overrides the path: a tab keeps its own tree when its
 * canonical route belongs to another mode (a reader child spawned inside a
 * research tree opens at /read/<doc>?m=research and stays a research tab).
 * documentSpace.routeForTab is the only writer of the parameter.
 */
export function mothershipForPath(pathname: string, search = ""): Mothership {
  const m = /[?&]m=(research|writing|reading)(?:&|$)/.exec(search);
  if (m) return m[1] as Mothership;
  if (pathname.startsWith("/read") || pathname.startsWith("/library")) return "reading";
  if (pathname.startsWith("/write")) return "writing";
  return "research";
}
