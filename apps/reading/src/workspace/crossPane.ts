/**
 * crossPane.ts — the C4→C5 seam: an agent in the companion (right pane)
 * opens a document in the LEFT pane.
 *
 * THE CONTRACT IS THE EVENT SHAPE, not the handler. As of cockpit PR 3 (D6)
 * the handler spawns a LEFT CHILD TAB under the current mothership's tab
 * tree (kind "reader", a "reference" branch origin) — the document opens in
 * the left document space via the strip's canonical-route navigation, never
 * as a window. PR 2's bridge (open/focus the reader window) is superseded;
 * any later handler (a dock lane, a split) swaps in through
 * setOpenDocumentHandler. Every caller speaks `openDocumentInLeftPane` and
 * never changes.
 */
import { childTabId, mothershipForPath, rootTabId } from "./documentSpace";
import { useTabTrees } from "./tabTreeStore";

export interface OpenDocumentOrigin {
  /** Where the request was born (e.g. "companion"). Metadata only. */
  from: string;
  investigationId?: string;
  agentTabId?: string;
}

export interface OpenDocumentRequest {
  documentId: string;
  origin: OpenDocumentOrigin;
}

/** The D6 handler: a left child tab under the spawning (active) tab — or a
 *  root tab when nothing is active. Re-opening the same document under the
 *  same parent ACTIVATES the existing tab (stable ids, never duplicates). */
function spawnDocumentTab(req: OpenDocumentRequest): void {
  const mothership = mothershipForPath(window.location.pathname);
  const store = useTabTrees.getState();
  void store.ensureMothership(mothership).then(() => {
    const s = useTabTrees.getState();
    const tree = s.trees[mothership];
    if (!tree) return;
    const parentId = tree.active_tab_id;
    const id = parentId
      ? childTabId(parentId, "reader", req.documentId)
      : rootTabId({ kind: "reader", ref: req.documentId, title: req.documentId });
    if (tree.nodes[id]) {
      s.activateTab(mothership, id);
      return;
    }
    s.spawnTab(mothership, parentId, {
      tab_id: id,
      origin: { document_id: req.documentId, kind: "reference" },
      kind: "reader",
      ref: req.documentId,
      mothership,
      activate: true,
    });
  });
}

let handler: (req: OpenDocumentRequest) => void = spawnDocumentTab;

/** The seam for any later handler (null restores the D6 default). Callers
 *  never change — they speak `openDocumentInLeftPane`, not trees or windows. */
export function setOpenDocumentHandler(
  next: ((req: OpenDocumentRequest) => void) | null,
): void {
  handler = next ?? spawnDocumentTab;
}

/** Open (focus) a document in the left pane. An empty identity is an honest
 *  no-op: no id, no tab, never a guessed target. */
export function openDocumentInLeftPane(
  documentId: string,
  origin: OpenDocumentOrigin,
): void {
  if (!documentId.trim()) return;
  handler({ documentId, origin });
}
