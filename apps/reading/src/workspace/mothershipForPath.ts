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

/** Each mode's home: where the screen goes when its tree has no open tab
 *  left (closing the last one), so the screen and the strip agree. */
export const MODE_HOME: Record<Mothership, string> = {
  research: "/",
  reading: "/library",
  writing: "/write",
};

/**
 * `to` with the mode of the page it is opened from. The ONE helper for an
 * in-app navigation that must keep the operator in their mode: a research
 * spun from a reader lives at /inv/<id>?m=reading, and a link or a launch
 * made from inside it opens in reading too. `?m` is added only when `to`
 * would otherwise file under another mode, and an explicit `?m` on `to`
 * always wins. Without a pinned mode on the current page, `to` is returned
 * unchanged.
 */
export function inMode(to: string, fromSearch: string): string {
  const pinned = /[?&]m=(research|writing|reading)(?:&|$)/.exec(fromSearch)?.[1] as Mothership | undefined;
  if (!pinned) return to;
  const hashAt = to.indexOf("#");
  const hash = hashAt === -1 ? "" : to.slice(hashAt);
  const bare = hashAt === -1 ? to : to.slice(0, hashAt);
  const qAt = bare.indexOf("?");
  const pathname = qAt === -1 ? bare : bare.slice(0, qAt);
  const query = qAt === -1 ? "" : bare.slice(qAt + 1);
  if (mothershipForPath(pathname, query ? `?${query}` : "") === pinned) return to;
  if (/(^|&)m=/.test(query)) return to;
  return `${pathname}?${query ? `${query}&` : ""}m=${pinned}${hash}`;
}
