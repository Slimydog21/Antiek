/**
 * Pure lineage-edge derivation for the DRW block-canvas (Living Roadmap
 * SPR-03 M3). Kept separate from the SVG component so the "render only what
 * the graph carries, never fabricate" rule (rigor #1) is mechanically
 * testable.
 *
 * THE LINEAGE GAP (load-bearing — see docs/decisions/spr-03-block-canvas-lineage.md):
 * the DRW graph carries NO insight→insight or question→insight relation among
 * the nodes of a single investigation. The only lineage signal that exists
 * today is `DistilledNode.reserved_child_investigation_id` — an escalated
 * question that RESERVED a deeper child research (the question→child-research
 * branch) — plus the investigation-level parent/child tree
 * (`useInvestigationTree`, via `parent_investigation_id`). Both are
 * investigation-scoped, not node-to-node. So on a single investigation's
 * canvas we draw exactly one honest edge kind: an escalated question block →
 * a "spawned a deeper research" child marker. We NEVER synthesize a
 * node-to-node edge from absent data. Where the relation is absent, there is
 * no edge — by construction, since we only iterate the fields that exist.
 *
 * EDGE GEOMETRY (intellectual honesty — see splinePath below): that one edge
 * kind is a VERTICAL drop — its endpoints share the parent block's center x
 * (Edges.tsx anchors `to` directly below `from`). So `splinePath` renders a
 * straight vertical segment for it; the bezier control points only bow when a
 * FUTURE node→node edge has endpoints that differ in x. Today there is no
 * active horizontal edge-separation — that capability is reserved, not in use.
 */

import type { DistilledNode } from "../../../lib/api";
import type { TreeNode } from "../../../hooks/useInvestigationTree";

/** A lineage edge to draw. `from` is always a node present on THIS canvas;
 *  `to` is either a sibling canvas node (none exist today) or a child-research
 *  marker the canvas renders as a leaf endpoint. */
export interface LineageEdge {
  /** Stable key for React. */
  id: string;
  /** The canvas node_id this edge starts at (always on-canvas). */
  fromNodeId: string;
  /** What the edge points to. `child_research` is the only kind the graph
   *  carries today; the discriminant lets a future node→node relation be
   *  added without reshaping consumers. */
  toKind: "child_research";
  /** The child investigation id the escalated question reserved/spawned. */
  toChildInvestigationId: string;
}

/**
 * Derive the lineage edges that the graph ACTUALLY carries for one
 * investigation's distilled nodes.
 *
 * `onCanvasNodeIds` is the set of node_ids actually rendered on the canvas;
 * an edge is emitted ONLY when its source node is on the canvas (the
 * "both-endpoints-present" discipline — there is no second on-canvas
 * endpoint for a child-research edge, so the source-present check is the
 * binding one). A question with no `reserved_child_investigation_id` produces
 * no edge — we never fabricate one to complete the picture.
 */
export function deriveLineageEdges(
  questions: DistilledNode[],
  onCanvasNodeIds: ReadonlySet<string>,
): LineageEdge[] {
  const edges: LineageEdge[] = [];
  for (const q of questions) {
    const child = q.reserved_child_investigation_id;
    // No reserved child → no lineage relation exists → no edge. (rigor #1)
    if (!child) continue;
    // Source must be on the canvas. (both-endpoints discipline)
    if (!onCanvasNodeIds.has(q.node_id)) continue;
    edges.push({
      id: `lineage:${q.node_id}->${child}`,
      fromNodeId: q.node_id,
      toKind: "child_research",
      toChildInvestigationId: child,
    });
  }
  return edges;
}

/**
 * Find, for a given investigation, its direct child investigations in the
 * investigation tree (`useInvestigationTree`'s shape). This is the OTHER real
 * lineage signal — investigation-level, not node-level. The canvas does not
 * draw node-to-node edges from it (no such relation exists), but a consumer
 * can use it to label which reserved child has actually LAUNCHED vs is merely
 * reserved. Returns the child investigation ids found under `investigationId`.
 *
 * Reused as-is from the shipped tree shape — we do NOT fork the data model.
 */
export function childInvestigationIds(
  tree: TreeNode[],
  investigationId: string,
): string[] {
  const node = findNode(tree, investigationId);
  if (!node) return [];
  return node.children.map((c) => c.investigationId);
}

function findNode(tree: TreeNode[], id: string): TreeNode | null {
  for (const n of tree) {
    if (n.investigationId === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}

/** A cubic-bezier path string between two points. Control points sit at each
 *  endpoint's x, on the vertical midpoint (midY).
 *
 *  TRUTH about today's edges (intellectual honesty): the ONLY edge the canvas
 *  draws is a vertical drop from an escalated question block to its
 *  child-research marker placed directly below it (Edges.tsx — both endpoints
 *  share the parent block's center x). Because from.x === to.x for that edge,
 *  this bezier collapses to a straight vertical segment — it does NOT bow, and
 *  there is no horizontal separation of overlapping edges today (there is only
 *  ever one such edge per parent).
 *
 *  The bezier form is RESERVED, not active: the SAME function will correctly
 *  bow when a FUTURE node→node edge has endpoints that differ in x (the control
 *  points then pull the curve through the vertical midpoint, giving an organic
 *  S rather than a diagonal straight line). Until such an edge exists, the
 *  curvature is latent. We do not claim active edge-separation that the current
 *  edge set does not exhibit. */
export function splinePath(
  from: { x: number; y: number },
  to: { x: number; y: number },
): string {
  const midY = (from.y + to.y) / 2;
  // Control points sit on each endpoint's x at the vertical midpoint. For
  // today's vertical edges (from.x === to.x) this is a straight drop; for a
  // future edge whose endpoints differ in x it bows through midY.
  return `M ${from.x} ${from.y} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${to.y}`;
}
