/**
 * Edges — the lineage layer of the DRW block-canvas (Living Roadmap SPR-03
 * M3). Hand-rolled SVG `<path>` splines between block centers; NO graph
 * library (see the react-flow-vs-SVG steelman in the sprint handoff).
 *
 * INTELLECTUAL HONESTY (rigor #1): this renders ONLY lineage the graph
 * actually carries. The single real node-anchored signal today is an escalated
 * question's `reserved_child_investigation_id` (a question → the deeper child
 * research it spawned). There is NO insight→insight / node→node lineage field
 * in the graph, so we draw none — `deriveLineageEdges` only iterates the
 * fields that exist, making fabrication structurally impossible. The
 * node-level-lineage gap is documented in
 * docs/decisions/spr-03-block-canvas-lineage.md.
 *
 * A child-research edge points from the question block to a small "spawned a
 * deeper research" marker placed just below the block — an HONEST edge-to-child
 * rather than a dangling edge to a node that isn't on this canvas.
 */

import type { DistilledNode } from "../../../lib/api";
import { BLOCK_HEIGHT, BLOCK_WIDTH, type BlockPosition } from "./canvasLayout";
import { deriveLineageEdges, splinePath } from "./edgeModel";

export interface EdgesProps {
  questions: DistilledNode[];
  /** node_id → resolved canvas position (top-left). */
  positions: Map<string, BlockPosition>;
  /** Total canvas extent so the SVG covers it. */
  width: number;
  height: number;
}

/** A child-research marker sits this far below its parent block's bottom. */
const CHILD_DROP = 64;

export default function Edges({ questions, positions, width, height }: EdgesProps) {
  const onCanvas = new Set(positions.keys());
  const edges = deriveLineageEdges(questions, onCanvas);

  // Nothing to draw — render no SVG at all (a single node / empty graph never
  // produces a phantom edge layer).
  if (edges.length === 0) return null;

  return (
    <svg
      data-testid="lineage-edges"
      className="pointer-events-none absolute inset-0"
      width={width}
      height={height}
      // The edge layer sits behind the blocks; blocks own pointer events.
      style={{ zIndex: 0 }}
      aria-hidden="true"
    >
      {edges.map((edge) => {
        const parent = positions.get(edge.fromNodeId);
        // Guard: the source must be positioned (it is, by deriveLineageEdges'
        // on-canvas check, but stay defensive — a missing position means no
        // honest place to anchor, so skip rather than draw to (0,0)).
        if (!parent) return null;
        const from = {
          x: parent.x + BLOCK_WIDTH / 2,
          y: parent.y + BLOCK_HEIGHT,
        };
        const to = {
          x: parent.x + BLOCK_WIDTH / 2,
          y: parent.y + BLOCK_HEIGHT + CHILD_DROP,
        };
        return (
          <g key={edge.id} data-edge-from={edge.fromNodeId} data-edge-to={edge.toChildInvestigationId}>
            <path
              d={splinePath(from, to)}
              fill="none"
              className="stroke-sun-deep dark:stroke-sun"
              strokeWidth={2}
              strokeDasharray="4 3"
            />
            {/* The child-research marker (the leaf endpoint). A circle + a
                tiny "deeper research" caption; honest about being a spawned
                child investigation, not a fabricated sibling node. */}
            <circle
              cx={to.x}
              cy={to.y}
              r={6}
              className="fill-sun-deep dark:fill-sun"
            />
            <text
              x={to.x + 10}
              y={to.y + 4}
              className="fill-shadow-1 dark:fill-moonlight"
              style={{ fontSize: 10, fontFamily: "ui-monospace, monospace" }}
            >
              spawned a deeper research
            </text>
          </g>
        );
      })}
    </svg>
  );
}
