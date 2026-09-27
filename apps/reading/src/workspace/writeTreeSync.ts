/**
 * writeTreeSync.ts — seeds the writing mothership's document tree (C5):
 * the deliverable's full body as tab 1, one child tab per section (1.1,
 * 1.2, …). Section tabs are sub-surfaces of the piece, NOT routes — their
 * refs deliberately do not start with "/", so activation never navigates to
 * a fabricated URL; WriteHome reads the active tab and scopes its view.
 * Idempotent: the piece's open tab is ADOPTED by its fields (the route sync
 * may have seeded it, as a new tab after a close), and existing section
 * tabs, found by their fields under it, are left alone. The piece's title
 * and section headings are registered as the tabs' titles here, so the strip
 * never shows a raw ref for a piece that is already loaded.
 */
import { useEffect } from "react";

import type { DeliverableDetailResponse } from "../lib/api";
import { findClosedTab, findOpenTab } from "./documentSpace";
import { SECTION_REF_PREFIX, sectionIdFromRef, sectionRefOf } from "./sectionRef";
import { newTabId } from "./tabId";
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
 * The open tab that shows the piece at `bodyRef`, found by its fields and
 * preferring a root: the route sync may have seeded it first, and after a
 * close the reseeded root is a new tab (critic P-C). Null when the piece has
 * no open tab.
 */
function openBodyTab(tree: TabTree, bodyRef: string): string | null {
  const root = findOpenTab(tree, { kind: "document", ref: bodyRef, parent_tab_id: null });
  if (root) return root;
  const shows = (id: string) => {
    const n = tree.nodes[id];
    return n.side === "left" && n.kind === "document" && n.ref === bodyRef;
  };
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
        bodyId = newTabId(tree);
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
        const fields = { kind: "document" as const, ref: sectionRefOf(section.section_id), parent_tab_id: bodyId };
        // An open section is left alone; a section the operator closed
        // (retired under this body) stays closed. Both found by fields.
        if (findOpenTab(tree, fields) !== null || findClosedTab(tree, fields) !== null) continue;
        useTabTrees.getState().spawnTab("writing", bodyId, {
          tab_id: newTabId(useTabTrees.getState().trees.writing ?? tree),
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
