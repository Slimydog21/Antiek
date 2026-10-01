/**
 * crossPane.ts — the C4→C5 seam: an agent in the companion (right pane)
 * opens a document in the LEFT pane.
 *
 * THE CONTRACT IS THE EVENT SHAPE, not the handler. As of cockpit PR 3 (D6)
 * the handler spawns a LEFT CHILD TAB under the current mothership's tab
 * tree (kind "reader"; origin kind "agent" with `opened_by` when an agent
 * thread opened it, §2.2 rev 7, else "reference") — the document opens in
 * the left document space via the strip's canonical-route navigation, never
 * as a window. PR 2's bridge (open/focus the reader window) is superseded;
 * any later handler (a dock lane, a split) swaps in through
 * setOpenDocumentHandler. Every caller speaks `openDocumentInLeftPane` and
 * never changes.
 */
import { toast } from "../components/lemon/LemonToast";
import { adoptTabForRoute, branchOriginOf, findOpenTab, mothershipForPath } from "./documentSpace";
import { adoptRoute } from "./routeSync";
import { newTabId } from "./tabId";
import { setTabTitle } from "./tabTitles";
import { locationStamp, useTabTrees } from "./tabTreeStore";
import { getTabOwner } from "./tabTreeOwner";

export interface OpenDocumentOrigin {
  /** Where the request was born (e.g. "companion"). Metadata only. */
  from: string;
  /** The agent's thread. With `agentKind`, the tab is agent-opened. */
  investigationId?: string;
  agentTabId?: string;
  /** The opening agent's kind (§2.2 `opened_by.agent_kind`: research,
   *  dialogue, reformat, diligence or island). */
  agentKind?: string;
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
  const pathname = window.location.pathname;
  const mothership = mothershipForPath(pathname, window.location.search);
  const requestedAt = locationStamp();
  const store = useTabTrees.getState();
  const contextEpoch = store.contextEpoch;
  const ownerEpoch = getTabOwner().epoch;
  const projectId = store.projectId;
  const companionOrigin = req.origin.from === "companion" && req.origin.agentTabId;
  const authorizedAgent = () => {
    if (!companionOrigin) return true;
    const state = useTabTrees.getState();
    const agent = state.trees[mothership]?.nodes[companionOrigin];
    return state.contextEpoch === contextEpoch && state.projectId === projectId && getTabOwner().epoch === ownerEpoch && !getTabOwner().suspended &&
      agent?.side === "right" && agent.ref === req.origin.investigationId && agent.kind === req.origin.agentKind;
  };
  if (!authorizedAgent()) return;
  // When the strip has loaded, resolve the route now: the active tab can
  // change even before ensureMothership's already-resolved promise settles.
  adoptRoute(mothership, pathname);
  const requestTree = useTabTrees.getState().trees[mothership];
  const requestParent = requestTree?.active_tab_id ?? null;
  const offerOpen = () => toast.info("A document is ready to open.", {
    action: { label: "Open document", run: () => spawnDocumentTab(req) },
  });
  void store.ensureMothership(mothership).then(() => {
    const s = useTabTrees.getState();
    // A source agent's authority ends with its owner/project binding or
    // tab. Never offer a retry that copies that provenance into another row.
    if (!authorizedAgent()) return;
    if (s.contextEpoch !== contextEpoch) {
      offerOpen();
      return;
    }
    const loadedTree = s.trees[mothership];
    if (!loadedTree) {
      offerOpen();
      return;
    }
    let tree = loadedTree;
    let parentId = requestParent;
    const parentRemoved = parentId !== null && !Object.hasOwn(tree.nodes, parentId);
    if (parentRemoved) parentId = null;
    if (!requestTree) {
      // Resolve the ORIGINAL route in the loaded tree without selecting it.
      // A late result must not change the tab the operator has since chosen.
      const adoption = adoptTabForRoute(tree, pathname);
      if (adoption.action === "none") parentId = tree.active_tab_id;
      else if (adoption.action === "activate") parentId = adoption.tabId;
      else {
        parentId = newTabId(tree);
        const seeded = s.spawnTab(mothership, adoption.action === "branch" ? adoption.parentId : null, {
          tab_id: parentId,
          kind: adoption.ref.kind,
          ref: adoption.ref.ref,
          mothership,
          ...(adoption.action === "branch" ? { origin: branchOriginOf(adoption.origin) } : {}),
          activate: false,
        }, "route");
        if (!seeded.ok) parentId = null;
        const seededTree = useTabTrees.getState().trees[mothership];
        if (!seededTree) {
          offerOpen();
          return;
        }
        tree = seededTree;
      }
    }
    const takeScreen = locationStamp() === requestedAt && !parentRemoved &&
      (!requestTree || tree.active_tab_id === requestParent);
    const notifyLateOpen = () => toast.info(`A document is ready in your ${mothership} tabs.`);
    const shows = (id: string) => tree.nodes[id].kind === "reader" && tree.nodes[id].ref === req.documentId;
    // Already the active tab: nothing to open.
    if (parentId && shows(parentId)) {
      if (takeScreen && tree.active_tab_id !== parentId) s.activateTab(mothership, parentId);
      else if (!takeScreen) notifyLateOpen();
      return;
    }
    // Found by its fields, never by its (opaque) id.
    const open = findOpenTab(tree, { side: "left", kind: "reader", ref: req.documentId, parent_tab_id: parentId });
    if (open) {
      if (takeScreen) s.activateTab(mothership, open);
      else notifyLateOpen();
      return;
    }
    if (req.documentTitle) setTabTitle("reader", req.documentId, req.documentTitle);
    // §2.2 rev 7 (S1): an agent-opened document is a LEFT node of origin
    // kind "agent" carrying opened_by {thread_id, agent_kind}, in the
    // current mode's tree. A request without a known agent thread (a
    // surface that is not an agent) stays a plain "reference" branch.
    const threadId = req.origin.investigationId?.trim();
    const agentKind = req.origin.agentKind?.trim();
    const agentOpened = threadId && agentKind ? { thread_id: threadId, agent_kind: agentKind } : null;
    const spawned = s.spawnTab(mothership, parentId, {
      tab_id: newTabId(tree),
      origin: { document_id: req.documentId, kind: agentOpened ? "agent" : "reference" },
      ...(agentOpened ? { opened_by: agentOpened } : {}),
      kind: "reader",
      ref: req.documentId,
      mothership,
      activate: takeScreen,
    });
    if (!spawned.ok) offerOpen();
    else if (!takeScreen) notifyLateOpen();
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
