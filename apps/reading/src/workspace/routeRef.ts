/**
 * routeRef.ts — the surface a record route IS, as a tab reference. Its own
 * module (no tab-tree model) so the Topbar can name a record route without
 * pulling the model into the entry chunk; documentSpace re-exports it.
 */
import type { TabKind } from "./tabTree";

export interface RootRef {
  kind: TabKind;
  ref: string;
}

/** First path segments under /read that are app surfaces, not documents
 *  (App.tsx: /read/meta-reading and /read/meta-reading/:assetId). */
const READ_SURFACES = new Set(["meta-reading"]);

export function segment(raw: string): string {
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
