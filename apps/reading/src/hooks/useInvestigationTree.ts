import { useEffect, useMemo, useState } from "react";

import type { InvestigationSummary } from "../lib/api";

const STORAGE_KEY = "antiek:investigation_tree";

export interface TreeNode {
  investigationId: string;
  summary: InvestigationSummary | null;
  children: TreeNode[];
}

interface TreeMap {
  [childId: string]: string; // childId → parentId
}

/**
 * Build a parent-child tree of investigations.
 *
 * Source of truth: the substrate emits ``parent_investigation_id`` in
 * each child's ``investigation.start_requested`` payload (Sprint 11
 * Day 1 substrate change). ``listInvestigations`` reads this back into
 * each summary's ``parent_investigation_id`` field. We additionally
 * maintain a localStorage map for cases where the substrate is offline
 * or hasn't surfaced the relationship yet.
 *
 * The hook merges both sources, with substrate truth winning over
 * localStorage. Orphans (children whose parent isn't in the list)
 * become roots.
 */
export function useInvestigationTree(
  investigations: InvestigationSummary[],
): TreeNode[] {
  const [localTree] = useState<TreeMap>(() => readLocalTree());

  const tree = useMemo<TreeNode[]>(() => {
    const byId = new Map<string, InvestigationSummary>();
    for (const s of investigations) byId.set(s.investigation_id, s);

    // Determine each investigation's parent: prefer substrate, fall
    // back to localStorage.
    const parentOf = new Map<string, string | null>();
    for (const s of investigations) {
      const p = s.parent_investigation_id ?? localTree[s.investigation_id] ?? null;
      parentOf.set(s.investigation_id, p);
    }

    // Build nodes.
    const nodes = new Map<string, TreeNode>();
    for (const s of investigations) {
      nodes.set(s.investigation_id, {
        investigationId: s.investigation_id,
        summary: s,
        children: [],
      });
    }
    // Attach to parents; orphans become roots.
    const roots: TreeNode[] = [];
    for (const node of nodes.values()) {
      const parentId = parentOf.get(node.investigationId);
      if (parentId && nodes.has(parentId)) {
        nodes.get(parentId)!.children.push(node);
      } else {
        roots.push(node);
      }
    }
    // Sort each level newest-first.
    const sortDesc = (nodes: TreeNode[]) => {
      nodes.sort((a, b) => {
        const ta = a.summary?.started_at ?? "";
        const tb = b.summary?.started_at ?? "";
        return tb.localeCompare(ta);
      });
      for (const n of nodes) sortDesc(n.children);
    };
    sortDesc(roots);
    return roots;
  }, [investigations, localTree]);

  return tree;
}

/**
 * Persist a parent → child relationship to localStorage. Called from
 * ChaseSlideOver after a successful spawn. Substrate is also recording
 * the same relationship via INVESTIGATION_SPAWNED_FROM events; this is
 * defensive belt-and-braces.
 */
export function recordSpawnRelationship(
  childId: string,
  parentId: string,
): void {
  const current = readLocalTree();
  current[childId] = parentId;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    // localStorage unavailable (private mode); the substrate's own
    // INVESTIGATION_SPAWNED_FROM event still carries the relationship.
  }
}

function readLocalTree(): TreeMap {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed as TreeMap;
  } catch {
    return {};
  }
}

// Force a re-read of localStorage from the consuming component when the
// storage event fires (multi-tab consistency).
export function useLocalTreeRefresh(refetch: () => void): void {
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) refetch();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [refetch]);
}

// Re-export the storage key for tests / debugging.
export const INVESTIGATION_TREE_STORAGE_KEY = STORAGE_KEY;
