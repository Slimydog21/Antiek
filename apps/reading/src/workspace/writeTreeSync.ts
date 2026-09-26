/**
 * writeTreeSync.ts — seeds the writing mothership's document tree (C5):
 * the deliverable's full body as tab 1, one child tab per section (1.1,
 * 1.2, …). Section tabs are sub-surfaces of the piece, NOT routes — their
 * refs deliberately do not start with "/", so activation never navigates to
 * a fabricated URL; WriteHome reads the active tab and scopes its view.
 * Idempotent: existing tabs (by stable id) are left alone.
 */
import { useEffect } from "react";

import type { DeliverableDetailResponse } from "../lib/api";
import { childTabId, rootTabId } from "./documentSpace";
import { useTabTrees } from "./tabTreeStore";

export const SECTION_REF_PREFIX = "section:";

export function sectionRefOf(sectionId: string): string {
  return `${SECTION_REF_PREFIX}${sectionId}`;
}

export function sectionIdFromRef(ref: string): string | null {
  return ref.startsWith(SECTION_REF_PREFIX) ? ref.slice(SECTION_REF_PREFIX.length) : null;
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
      const bodyId = rootTabId({ kind: "document", ref: bodyRef, title: detail.title });
      let s = useTabTrees.getState();
      let tree = s.trees.writing;
      if (!tree) return;
      if (!tree.nodes[bodyId]) {
        s.spawnTab("writing", null, {
          tab_id: bodyId,
          kind: "document",
          ref: bodyRef,
          mothership: "writing",
          activate: false,
        });
      }
      tree = useTabTrees.getState().trees.writing;
      if (!tree) return;
      for (const section of [...detail.sections].sort(
        (a, b) => a.section_index - b.section_index,
      )) {
        const cid = childTabId(bodyId, "document", sectionRefOf(section.section_id));
        if (!tree.nodes[cid]) {
          useTabTrees.getState().spawnTab("writing", bodyId, {
            tab_id: cid,
            kind: "document",
            ref: sectionRefOf(section.section_id),
            mothership: "writing",
            activate: false,
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [detail]);
}
