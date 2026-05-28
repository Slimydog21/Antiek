/**
 * Edges.test.tsx — DRW block-canvas M3 acceptance: lineage edges from EXISTING
 * relations only, NEVER fabricated (rigor #1).
 *
 * Pins the criteria:
 *  - a branched fixture (an escalated question with a reserved child research)
 *    produces the parent→child edge, anchored on the question block;
 *  - a question with NO reserved child produces NO edge (absent relation →
 *    no edge, the canvas never fabricates one);
 *  - a question whose block is NOT on the canvas produces no edge
 *    (both-endpoints / source-present discipline);
 *  - the rendered edge anchors at the parent block center and ends at the
 *    child marker directly below it (so a wrong-endpoint edge would fail);
 *  - splinePath is faithful to its endpoints: it bows only when endpoints
 *    differ in x (a reserved future node→node edge) and collapses to a
 *    straight vertical segment for today's only edge (endpoints share x).
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import Edges from "./Edges";
import { deriveLineageEdges, childInvestigationIds, splinePath } from "./edgeModel";
import { BLOCK_HEIGHT, BLOCK_WIDTH, type BlockPosition } from "./canvasLayout";
import type { DistilledNode } from "../../../lib/api";
import type { TreeNode } from "../../../hooks/useInvestigationTree";

function question(node_id: string, extra: Partial<DistilledNode> = {}): DistilledNode {
  return {
    node_id,
    kind: "question",
    text: `Q ${node_id}`,
    confidence: null,
    source_document_id: null,
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
    ...extra,
  };
}

function pos(x: number, y: number): BlockPosition {
  return { x, y, regionId: null, regionLabel: null, persisted: false };
}

describe("deriveLineageEdges — render what exists, never fabricate (M3 / rigor #1)", () => {
  it("emits an edge for an escalated question that reserved a child research", () => {
    const qs = [question("q1", { escalated: true, reserved_child_investigation_id: "inv-child" })];
    const edges = deriveLineageEdges(qs, new Set(["q1"]));
    expect(edges).toHaveLength(1);
    expect(edges[0].fromNodeId).toBe("q1");
    expect(edges[0].toKind).toBe("child_research");
    expect(edges[0].toChildInvestigationId).toBe("inv-child");
  });

  it("emits NO edge for a question with no reserved child (absent relation)", () => {
    const qs = [question("q1", { reserved_child_investigation_id: null })];
    expect(deriveLineageEdges(qs, new Set(["q1"]))).toHaveLength(0);
  });

  it("emits NO edge when the source node is not on the canvas (both-endpoints discipline)", () => {
    const qs = [question("q1", { reserved_child_investigation_id: "inv-child" })];
    expect(deriveLineageEdges(qs, new Set(["other"]))).toHaveLength(0);
  });
});

describe("childInvestigationIds — investigation-level tree, reused not forked", () => {
  it("reads direct children from the useInvestigationTree shape", () => {
    const tree: TreeNode[] = [
      {
        investigationId: "root",
        summary: null,
        children: [
          { investigationId: "child-a", summary: null, children: [] },
          { investigationId: "child-b", summary: null, children: [] },
        ],
      },
    ];
    expect(childInvestigationIds(tree, "root")).toEqual(["child-a", "child-b"]);
    expect(childInvestigationIds(tree, "missing")).toEqual([]);
  });
});

describe("splinePath — geometry is faithful to its endpoints (rigor #3)", () => {
  it("starts at `from` and ends at `to` (a future node→node edge bows in x)", () => {
    // Endpoints that differ in x → the bezier control points bow through midY,
    // so the curve is not a straight diagonal. This is the RESERVED bow path.
    const d = splinePath({ x: 10, y: 20 }, { x: 40, y: 120 });
    expect(d.startsWith("M 10 20")).toBe(true); // M-start === from
    expect(d.endsWith("40 120")).toBe(true); // C-end === to
    const midY = (20 + 120) / 2; // 70
    // Control points sit on each endpoint's x at midY (so it bows, not a line).
    expect(d).toBe(`M 10 20 C 10 ${midY}, 40 ${midY}, 40 120`);
  });

  it("collapses to a straight VERTICAL segment when from.x === to.x (today's only edge)", () => {
    // The honest truth: the only edge drawn today is a vertical drop
    // (endpoints share x), so the bezier is geometrically a straight line.
    const d = splinePath({ x: 220, y: 196 }, { x: 220, y: 260 });
    const midY = (196 + 260) / 2; // 228
    expect(d).toBe(`M 220 196 C 220 ${midY}, 220 ${midY}, 220 260`);
    // All x coordinates equal → no horizontal deviation → a vertical segment.
  });
});

describe("Edges (SVG) — renders only real edges", () => {
  it("anchors the edge from the parent block center to the child marker below it", () => {
    const qs = [question("q1", { reserved_child_investigation_id: "inv-child" })];
    const positions = new Map<string, BlockPosition>([["q1", pos(100, 100)]]);
    const { getByTestId, container } = render(
      <Edges questions={qs} positions={positions} width={800} height={600} />,
    );
    expect(getByTestId("lineage-edges")).toBeTruthy();
    const group = container.querySelector('[data-edge-from="q1"]');
    expect(group).toBeTruthy();
    expect(group!.getAttribute("data-edge-to")).toBe("inv-child");

    // The REAL edge shape: M-start is the parent block's bottom-center, the
    // C-end is the child marker CHILD_DROP px directly below it. Asserting both
    // endpoints means the test fails if the edge were drawn between the wrong
    // points (e.g. to (0,0) or from a different block). CHILD_DROP = 64 in
    // Edges.tsx; the marker x must equal the from x (a vertical drop).
    const CHILD_DROP = 64;
    const fromX = 100 + BLOCK_WIDTH / 2; // parent center x
    const fromY = 100 + BLOCK_HEIGHT; // parent bottom
    const toX = fromX; // same x → vertical
    const toY = fromY + CHILD_DROP;
    const path = container.querySelector("path");
    expect(path).toBeTruthy();
    const d = path!.getAttribute("d")!;
    expect(d.startsWith(`M ${fromX} ${fromY}`)).toBe(true);
    expect(d.endsWith(`${toX} ${toY}`)).toBe(true);

    // And the marker circle is at the to point (the honest leaf endpoint).
    const circle = container.querySelector("circle");
    expect(circle!.getAttribute("cx")).toBe(String(toX));
    expect(circle!.getAttribute("cy")).toBe(String(toY));
  });

  it("renders NO svg at all when there are no real edges (single node / empty graph)", () => {
    const qs = [question("q1", { reserved_child_investigation_id: null })];
    const positions = new Map<string, BlockPosition>([["q1", pos(100, 100)]]);
    const { container } = render(
      <Edges questions={qs} positions={positions} width={800} height={600} />,
    );
    expect(container.querySelector('[data-testid="lineage-edges"]')).toBeNull();
  });
});
