/**
 * routeSync.ts — the route → tree sync (documentSpace.adoptTabForRoute
 * applied to the store), shared by the document strip's route effect, its
 * "Try again", and the cross-pane seam. Every activation it makes is a
 * "route" activation: it follows a navigation that already happened and
 * never starts one (tabTreeStore.ActivationSource).
 *
 * The cross-pane seam runs it before choosing a parent, so an agent open
 * that lands before the strip has seeded the route's tab (the strip loads
 * lazily) still files under the tab showing the route, never as a root.
 */
import type { BranchIntent } from "./branchNavigation";
import { adoptTabForRoute, branchOriginOf } from "./documentSpace";
import { newTabId } from "./tabId";
import type { Mothership } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";

/** Load `mothership`'s tree, then adopt `pathname` into it. A navigation
 *  that carries a branch intent (branchNavigation) files its surface under
 *  the tab it was triggered from. */
export async function syncRouteToTree(
  mothership: Mothership,
  pathname: string,
  intent: BranchIntent | null = null,
): Promise<void> {
  await useTabTrees.getState().ensureMothership(mothership);
  adoptRoute(mothership, pathname, intent);
}

/** The synchronous half, for a caller whose tree is already loaded. */
export function adoptRoute(mothership: Mothership, pathname: string, intent: BranchIntent | null = null): void {
  const store = useTabTrees.getState();
  const tree = store.trees[mothership];
  if (!tree) return;
  const adoption = adoptTabForRoute(tree, pathname, intent);
  if (adoption.action === "activate") store.activateTab(mothership, adoption.tabId, "route");
  else if (adoption.action === "seed") {
    store.spawnTab(
      mothership,
      null,
      {
        tab_id: newTabId(tree),
        kind: adoption.ref.kind,
        ref: adoption.ref.ref,
        mothership,
        activate: true,
      },
      "route",
    );
  } else if (adoption.action === "branch") {
    store.spawnTab(
      mothership,
      adoption.parentId,
      {
        tab_id: newTabId(tree),
        origin: branchOriginOf(adoption.origin),
        kind: adoption.ref.kind,
        ref: adoption.ref.ref,
        mothership,
        activate: true,
      },
      "route",
    );
  }
}
