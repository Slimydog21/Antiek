/**
 * islandModel.ts — the research-thread island's pure model (island SPR-01).
 *
 * Two pure pieces, no I/O:
 *
 *   deriveIslandRefs — from the unit-1 anchor list, the anchors that HOLD a
 *   thread (non-null investigation_id — the SPR-04 seam the spawn write-back
 *   fills) become IslandRefs: the island's anchor identity (passage anchor +
 *   servability) plus the thread it hangs from. Anchors with no thread are
 *   plain highlights, never islands.
 *
 *   islandStatus — the EXPLICIT, TOTAL status mapping (the spec's contract).
 *   Canonical truth is the investigation EVENT PROJECTION (useInvestigation);
 *   the summary status (the family list's InvestigationSummary) refines the
 *   stopped case; the session-level ResearchRunState refines further WHEN
 *   resolvable (there is no session-for-investigation lookup route today, so
 *   "resolvable" means the thread is itself a session container). Terminal
 *   authority is TERMINAL_STATES (api/research.ts:94-96). "not_found" maps to
 *   an honest gone — the thread record is missing; the island says so, never
 *   fabricates a status for it.
 */
import type { ResearchRunState } from "../../../api/research";
import { TERMINAL_STATES } from "../../../api/research";
import type { BookAnchor } from "../../../lib/api";
import type { InvestigationSummary } from "../../../lib/api";
import type { TreeNode } from "../../../hooks/useInvestigationTree";

/** The island's anchor identity + the thread it hangs from. */
export interface IslandRef {
  anchorId: string;
  documentId: string;
  /** The unit-1 passage anchor the island is pinned to (chunk-relative). */
  passageAnchor: { chunkId: string; start: number; end: number };
  investigationId: string;
  servable: boolean;
}

/** The island's status vocabulary (the spec's closed set). */
export type IslandStatus =
  | "live"
  | "complete"
  | "complete_empty"
  | "failed"
  | "stopped"
  | "budget_halted"
  | "gone";

/** The statuses that are TERMINAL — an island in one never spins again. */
export const ISLAND_TERMINAL_STATUSES: ReadonlySet<IslandStatus> = new Set([
  "complete",
  "complete_empty",
  "failed",
  "stopped",
  "budget_halted",
  "gone",
]);

/** Derive the islands from the anchor list: exactly the anchors carrying a
 *  thread link. (Anchors with a null investigation_id are highlights, not
 *  islands — first-link-wins means at most one island per anchor by
 *  construction.) */
export function deriveIslandRefs(anchors: readonly BookAnchor[]): IslandRef[] {
  return anchors
    .filter((a) => a.investigation_id !== null)
    .map((a) => ({
      anchorId: a.anchor_id,
      documentId: a.document_id,
      passageAnchor: {
        chunkId: a.anchor.node_id,
        start: a.anchor.start_scalar,
        end: a.anchor.end_scalar,
      },
      investigationId: a.investigation_id as string,
      servable: a.servable_at_pin,
    }));
}

/** The three status sources the mapping arbitrates (all already-loaded
 *  data — no new fetches beyond what the hook composes). */
export interface IslandStatusInput {
  /** The event projection (useInvestigation). null = still loading. */
  projection: "loading" | "in_progress" | "completed" | "failed" | "not_found" | null;
  /** The family-list summary status, when the thread is in the loaded page. */
  summary: InvestigationSummary["status"] | null;
  /** The session-level run state, when the owning session is resolvable. */
  session: ResearchRunState | null;
  /** Insights the thread produced (the distill projection). null = not yet
   *  fetched — the hook reports outcomeLoading alongside. */
  insightCount: number | null;
}

function assertNeverIsland(x: never): never {
  throw new Error(`unmapped island status input: ${String(x)}`);
}

/**
 * The total mapping — an ordered rule list (first match wins), so EVERY
 * projection × session × summary combination lands on exactly one island
 * status. A future enum member breaks tsc at the call sites AND fails the
 * exhaustive-mapping test loudly.
 */
export function islandStatus(input: IslandStatusInput): IslandStatus {
  // 1. The projection's missing record is the strongest authority: gone.
  if (input.projection === "not_found") return "gone";
  // 2. The session's terminal vocabulary refines when resolvable
  //    (TERMINAL_STATES is the terminal authority).
  if (input.session === "budget_halted") return "budget_halted";
  if (input.session === "failed") return "failed";
  if (input.session === "stopped") return "stopped";
  // 3. Any failed source reads failed honestly.
  if (input.projection === "failed" || input.summary === "failed") return "failed";
  // 4. A stopped/halted thread (the summary's terminal vocabulary) is
  //    stopped — never a spinner forever.
  if (input.summary === "stopped") return "stopped";
  // 5. Any completion is complete vs complete_empty by the distill
  //    projection: zero insights is complete_empty — an honest terminal,
  //    NOT an error.
  if (
    input.session === "done" ||
    input.projection === "completed" ||
    input.summary === "completed"
  ) {
    return input.insightCount === 0 ? "complete_empty" : "complete";
  }
  // 6. A KNOWN live signal is live: the projection still loading or in
  //    progress (including the all-null initial state), the summary in
  //    progress, or a non-terminal session state. Deliberately NOT "anything
  //    else": a future status this table doesn't know must NOT silently map
  //    to live — it falls through and fails loudly below.
  if (
    input.projection === null ||
    input.projection === "loading" ||
    input.projection === "in_progress" ||
    input.summary === "in_progress" ||
    input.session === "pending" ||
    input.session === "running" ||
    input.session === "paused" ||
    input.session === "stopping"
  ) {
    return "live";
  }
  return assertNeverIsland(input as never);
}

/** A flattened family node (the tree view's row): the thread, its depth in
 *  the family, and its summary status. */
export interface IslandFamilyNode {
  investigationId: string;
  depth: number;
  status: InvestigationSummary["status"] | null;
  question: string | null;
}

/**
 * The island's thread family: the ROOT (the topmost loaded ancestor of the
 * island's investigation) and every chase below it, flattened pre-order.
 * Built on useInvestigationTree's merged tree — substrate parent ids win
 * over the localStorage fallback, so the family follows the tree's own
 * merge rule, never a re-derivation. When the island's investigation isn't
 * in the loaded list, the family is the honest single node the projection
 * knows (never a fabricated lineage).
 */
export function selectIslandFamily(
  roots: readonly TreeNode[],
  investigationId: string,
): IslandFamilyNode[] {
  function find(nodes: readonly TreeNode[], id: string): TreeNode | null {
    for (const node of nodes) {
      if (node.investigationId === id) return node;
      const inChildren = find(node.children, id);
      if (inChildren) return inChildren;
    }
    return null;
  }
  function rootOf(nodes: readonly TreeNode[], id: string): TreeNode | null {
    for (const node of nodes) {
      if (find([node], id)) return node;
    }
    return null;
  }
  const target = find(roots, investigationId);
  const familyRoot = target ? rootOf(roots, investigationId) : null;
  const out: IslandFamilyNode[] = [];
  function walk(node: TreeNode, depth: number): void {
    out.push({
      investigationId: node.investigationId,
      depth,
      status: node.summary?.status ?? null,
      question: node.summary?.question ?? null,
    });
    for (const child of node.children) walk(child, depth + 1);
  }
  if (familyRoot) walk(familyRoot, 0);
  return out;
}

/** Re-export so consumers read the terminal authority from one place. */
export { TERMINAL_STATES };
