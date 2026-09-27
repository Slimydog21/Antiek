/**
 * tabTestKit.ts — test helpers for trees whose tab_ids are opaque (A2b):
 * a test finds a tab by what it shows and where it hangs, exactly as the
 * product does (documentSpace.findOpenTab), never by building its id.
 */
import { findOpenTab, type TabFields } from "./documentSpace";
import type { TabKind, TabTree } from "./tabTree";

/** The open tab showing `kind`/`ref`, under `parent` (default: a root). Throws
 *  when there is none, so an assertion on its result can never pass vacuously. */
export function tabIdOf(
  tree: TabTree,
  kind: TabKind,
  ref: string,
  parent: string | null = null,
  side: TabFields["side"] = "left",
): string {
  const id = findOpenTab(tree, { side, kind, ref, parent_tab_id: parent });
  if (id === null) {
    const open = Object.values(tree.nodes).map((n) => `${n.tab_id}(${n.kind} ${n.ref} under ${n.parent_tab_id})`);
    throw new Error(`no open ${kind} tab for ${ref} under ${parent ?? "the roots"}; open: ${open.join(", ") || "none"}`);
  }
  return id;
}
