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
import { findOpenTab, mothershipForPath } from "./documentSpace";
import { adoptRoute } from "./routeSync";
import { newTabId } from "./tabId";
import { setTabTitle } from "./tabTitles";
import { locationStamp, useTabTrees } from "./tabTreeStore";
import { useWorkspace } from "./WorkspaceStore";

/** A tab that takes the screen must be on it: where one pane shows at a
 *  time (the inset at tier md) and the left is offstage, bring it on
 *  (stage B3-3). Elsewhere the left pane is already on screen and the focus
 *  ring stays where the operator put it. */
function revealLeftPane(): void {
  if (document.querySelector('[data-pane="left"]')?.hasAttribute("data-pane-offstage")) {
    useWorkspace.getState().setFocusedPane("left");
  }
}

export interface OpenDocumentOrigin {
  /** Where the request was born (e.g. "companion"). Metadata only. */
  from: string;
  investigationId?: string;
  agentTabId?: string;
}

export interface OpenDocumentRequest {
  documentId: string;
  origin: OpenDocumentOrigin;
  /** The document's title when the caller knows it (the tab shows it at
   *  once); absent, the strip resolves it from the corpus. */
  documentTitle?: string | null;
}

/** The D6 handler: a left child tab under the spawning (active) tab — or a
 *  root tab when nothing is active. Re-opening the same document under the
 *  same parent ACTIVATES the open tab (never a duplicate), found by its
 *  fields; reopening one that was closed opens a new tab (a new opaque id:
 *  the closed one stays in history). */
function spawnDocumentTab(req: OpenDocumentRequest): void {
  const mothership = mothershipForPath(window.location.pathname, window.location.search);
  const requestedAt = locationStamp();
  const store = useTabTrees.getState();
  void store.ensureMothership(mothership).then(() => {
    // The operator navigated while the tree loaded: the tab still opens (an
    // agent's find is never dropped) but does not take the screen from the
    // navigation they made since (F-04).
    const takeScreen = locationStamp() === requestedAt;
    // The tab showing the route is the parent: adopt the route first, in
    // case the (lazy) strip has not seeded it yet — a no-op when it has.
    adoptRoute(mothership, window.location.pathname);
    const s = useTabTrees.getState();
    const tree = s.trees[mothership];
    if (!tree) return;
    const parentId = tree.active_tab_id;
    const parent = parentId ? tree.nodes[parentId] : null;
    // Already the active tab: nothing to open; only make sure it is seen.
    if (parent && parent.side === "left" && parent.kind === "reader" && parent.ref === req.documentId) {
      if (takeScreen) revealLeftPane();
      return;
    }
    // Found by its fields, never by its (opaque) id.
    const open = findOpenTab(tree, { side: "left", kind: "reader", ref: req.documentId, parent_tab_id: parentId });
    if (open) {
      if (takeScreen) {
        s.activateTab(mothership, open);
        revealLeftPane();
      }
      return;
    }
    if (req.documentTitle) setTabTitle("reader", req.documentId, req.documentTitle);
    s.spawnTab(mothership, parentId, {
      tab_id: newTabId(tree),
      origin: { document_id: req.documentId, kind: "reference" },
      kind: "reader",
      ref: req.documentId,
      mothership,
      activate: takeScreen,
    });
    if (takeScreen) revealLeftPane();
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
  documentTitle?: string | null,
): void {
  if (!documentId.trim()) return;
  handler({ documentId, origin, ...(documentTitle ? { documentTitle } : {}) });
}
