/**
 * writeTreeSync.ts — seeds the writing mothership's document tree (C5):
 * the deliverable's full body as tab 1, one child tab per section (1.1,
 * 1.2, …). Section tabs are sub-surfaces of the piece, NOT routes — their
 * refs deliberately do not start with "/", so activation never navigates to
 * a fabricated URL; WriteHome reads the active tab and scopes its view.
 * Idempotent: the piece's open tab is ADOPTED by ref (the route sync may
 * have seeded it, under a fresh id after a close), and existing section tabs
 * are left alone. The piece's title and section headings are registered as
 * the tabs' titles here, so the strip never shows a raw ref for a piece
 * that is already loaded.
 */
import { useEffect } from "react";

import type { DeliverableDetailResponse } from "../lib/api";
import { childTabId, freshTabId, rootTabId } from "./documentSpace";
import { SECTION_REF_PREFIX, sectionIdFromRef, sectionRefOf } from "./sectionRef";
import { registerDeliverableTitles } from "./tabTitles";
import type { TabNode, TabTree } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";

export { SECTION_REF_PREFIX, sectionIdFromRef, sectionRefOf };

/**
 * The section a Write piece's view scopes to: the active tab's section when
 * that section belongs to THIS piece, else null (the full outline). A
 * section tab of another piece never filters this piece's sections down to
 * nothing (critic P-B).
 */
export function sectionScopeFor(
  activeTab: Pick<TabNode, "kind" | "ref"> | null | undefined,
  sections: readonly { section_id: string }[],
): string | null {
  if (!activeTab || activeTab.kind !== "document") return null;
  const id = sectionIdFromRef(activeTab.ref);
  return id !== null && sections.some((s) => s.section_id === id) ? id : null;
}

/**
 * The open tab that shows the piece at `bodyRef`, preferring a root: the
 * route sync may have seeded it first, and after a close the reseeded root
 * carries a fresh id (`base~2`), since the closed id stays in history
 * (critic P-C). Null when the piece has no open tab.
 */
function openBodyTab(tree: TabTree, bodyRef: string): string | null {
  const shows = (id: string) =>
    Object.hasOwn(tree.nodes, id) && tree.nodes[id].kind === "document" && tree.nodes[id].ref === bodyRef;
  const root = tree.root_order.find(shows);
  if (root) return root;
  return Object.keys(tree.nodes).find(shows) ?? null;
}

export function useWriteTreeSync(detail: DeliverableDetailResponse | null) {
  useEffect(() => {
    if (!detail) return;
    let cancelled = false;
    void (async () => {
      const store = useTabTrees.getState();
      await store.ensureMothership("writing");
      if (cancelled) return;
      const bodyRef = `/write/${detail.deliverable_id}`;
      registerDeliverableTitles(detail);
      let tree = useTabTrees.getState().trees.writing;
      if (!tree) return;
      let bodyId = openBodyTab(tree, bodyRef);
      if (bodyId === null) {
        bodyId = freshTabId(tree, rootTabId({ kind: "document", ref: bodyRef }));
        const seeded = useTabTrees.getState().spawnTab("writing", null, {
          tab_id: bodyId,
          kind: "document",
          ref: bodyRef,
          mothership: "writing",
          activate: false,
        });
        if (!seeded.ok) return;
      }
      tree = useTabTrees.getState().trees.writing;
      if (!tree) return;
      for (const section of [...detail.sections].sort(
        (a, b) => a.section_index - b.section_index,
      )) {
        const cid = childTabId(bodyId, "document", sectionRefOf(section.section_id));
        // An open section is left alone; a section the operator closed
        // (its id is in history) stays closed.
        if (Object.hasOwn(tree.nodes, cid) || Object.hasOwn(tree.history, cid)) continue;
        useTabTrees.getState().spawnTab("writing", bodyId, {
          tab_id: cid,
          kind: "document",
          ref: sectionRefOf(section.section_id),
          mothership: "writing",
          activate: false,
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [detail]);
}
