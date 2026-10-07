/**
 * newTab.ts — the prefix+c picker's spawn (the D2 "new tab" key): a
 * document or an investigation as a fresh ROOT tab in its own mothership's
 * tree, shown at once.
 *
 * THE CONTRACT IS ONE FUNCTION, `spawnNewTab`. The picker (NewTabPicker)
 * is the only caller; any later surface (a strip menu, a drag target) takes
 * the same function, so "new tab" never grows a second spawn path beside
 * this one and the cross-pane seam (crossPane.ts, which spawns child tabs
 * from agent opens — a different gesture, a different place in the tree).
 *
 * Semantics, in the model's terms (tabTree.ts):
 *   - A pick is a USER activation: spawnTab requests the navigation, the
 *     document strip's nav effect performs it, so a pick, a strip click
 *     and a tab key take one path (tabTreeStore.ActivationSource).
 *   - The tab is a ROOT of the surface's own mothership (a document under
 *     reading, an investigation under research): "new tab" is a new
 *     top-level context, never a branch of whatever is on screen.
 *   - A surface already open is ACTIVATED, never duplicated (the
 *     cross-pane seam's rule): "new tab" for what you have takes you back
 *     to the tab you have. A surface only closed takes a fresh id, because
 *     the closed id stays in history (documentSpace.freshTabId).
 *   - The corpus is account-wide; the project selection scopes only the
 *     trees. A project switch mid-open therefore re-loads once under the
 *     new context and files the tab there, instead of dying silently.
 */
import { toast } from "../components/lemon/LemonToast";
import { isWorkspaceOwnerSession, workspaceOwnerSession } from "../lib/accountWorkspaceOwner";
import { freshTabId, rootTabId } from "./documentSpace";
import { setTabTitle } from "./tabTitles";
import { useTabTrees } from "./tabTreeStore";
import { subtreeIds, type Mothership } from "./tabTree";

/** What the picker can open as a new tab: the corpus-backed kinds, each
 *  with its own mothership. (The writing tree grows from the Write routes'
 *  own sync — writeTreeSync — not from a corpus list, so it has no pick
 *  here.) */
export interface NewTabTarget {
  kind: "reader" | "research";
  /** The surface's ref, in routeRef's shape: the bare document id for a
   *  reader, `/inv/<id>` for an investigation. */
  ref: string;
  /** The title the tab shows at once; the strip's resolver refines it. */
  title?: string | null;
}

const MOTHERSHIP_OF: Record<NewTabTarget["kind"], Mothership> = {
  reader: "reading",
  research: "research",
};

/** Open `target` as the tree's active root tab (or activate the open tab
 *  that already shows it). Never rejects: a failed load is the strip's own
 *  error state, a failed spawn a toast; the operator is never left with a
 *  picker that closed into silence. */
export async function spawnNewTab(target: NewTabTarget): Promise<void> {
  const owner = workspaceOwnerSession();
  const mothership = MOTHERSHIP_OF[target.kind];
  const contextEpoch = useTabTrees.getState().contextEpoch;
  await useTabTrees.getState().ensureMothership(mothership);
  if (!isWorkspaceOwnerSession(owner)) return;
  let s = useTabTrees.getState();
  if (s.contextEpoch !== contextEpoch) {
    // The project (or adapter) changed mid-load: load once under the new
    // context and file the tab there — the corpus is account-wide, so the
    // target survives the switch.
    await s.ensureMothership(mothership);
    if (!isWorkspaceOwnerSession(owner)) return;
    s = useTabTrees.getState();
  }
  const tree = s.trees[mothership];
  if (!tree) {
    toast.warn("Couldn't open your tabs. Your documents are untouched; try again from the tab strip.");
    return;
  }
  const shows = (id: string) => tree.nodes[id].kind === target.kind && tree.nodes[id].ref === target.ref;
  for (const root of tree.root_order) {
    const open = [root, ...subtreeIds(tree, root)].find(shows);
    if (open) {
      s.activateTab(mothership, open);
      return;
    }
  }
  if (target.title) setTabTitle(target.kind, target.ref, target.title);
  const spawned = s.spawnTab(mothership, null, {
    tab_id: freshTabId(tree, rootTabId({ kind: target.kind, ref: target.ref })),
    kind: target.kind,
    ref: target.ref,
    mothership,
    activate: true,
  });
  if (!spawned.ok) toast.warn(spawned.error ?? "That tab could not be opened.");
}
