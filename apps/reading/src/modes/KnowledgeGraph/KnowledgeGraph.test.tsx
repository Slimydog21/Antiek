import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import KnowledgeGraph from "./index";

const exploreGraph = vi.fn<typeof import("../../api/graph").exploreGraph>();

vi.mock("../../api/graph", async () => {
  const actual = await vi.importActual<typeof import("../../api/graph")>("../../api/graph");
  return { ...actual, exploreGraph: (...args: Parameters<typeof actual.exploreGraph>) => exploreGraph(...args) };
});

const response = {
  query: "",
  node_type: null,
  graph_scope: null,
  investigation_id: null,
  node_count: 2,
  edge_count: 1,
  truncated: false,
  read_only: true as const,
  view_format: "html" as const,
  nodes: [
    { node_id: "insight-1", label: "Cited reuse compounds knowledge", node_type: "insight", graph_scope: "depth", degree: 3, created_at: "2026-07-12" },
    { node_id: "mechanism-1", label: "Recursive memory", node_type: "mechanism", graph_scope: "cross_domain", degree: 2, created_at: "2026-07-12" },
  ],
  edges: [
    {
      edge_id: "edge-1",
      source_node_id: "insight-1",
      source_label: "Cited reuse compounds knowledge",
      target_node_id: "mechanism-1",
      target_label: "Recursive memory",
      relation: "explains",
      graph_scope: "depth",
      investigation_id: "inv-1",
      confidence: 0.94,
      valid_from: "2026-07-12",
      valid_until: null,
      evidence: {
        chunk_id: "chunk-1",
        chunk_text: "Evidence supports graph reuse.",
        section_path: "Results",
        source_document_id: "doc-1",
        source_title: "Public paper",
        source_author: "A. Researcher",
        source_tier: 1,
        content_class: "public_domain",
        ip_holder_id: null,
        servable: true,
      },
    },
  ],
};

describe("KnowledgeGraph", () => {
  beforeEach(() => exploreGraph.mockReset());
  afterEach(cleanup);

  it("traces a selected node through an edge to exact evidence", async () => {
    exploreGraph.mockResolvedValue(response);
    render(<KnowledgeGraph />);

    await screen.findByTestId("graph-node-insight-1");
    expect(screen.getByTestId("knowledge-graph").getAttribute("data-read-only")).toBe("true");
    expect(screen.getByTestId("graph-counts").textContent).toMatch(/2 nodes · 1 adjacent edge/);
    expect(screen.getByTestId("graph-edge-edge-1").textContent).toMatch(/explains/i);
    const rail = screen.getByTestId("graph-evidence-rail");
    expect(rail.textContent).toMatch(/chunk-1/);
    expect(rail.textContent).toMatch(/Evidence supports graph reuse/);
    expect(rail.textContent).toMatch(/Public paper/);
    expect(rail.textContent).toMatch(/Servable in portable output/);

    fireEvent.click(screen.getByTestId("graph-node-mechanism-1"));
    expect(screen.getByText("Recursive memory", { selector: "h2" })).toBeTruthy();
  });

  it("submits explicit filters and renders an honest empty state", async () => {
    exploreGraph
      .mockResolvedValueOnce(response)
      .mockResolvedValueOnce({ ...response, query: "missing", node_count: 0, edge_count: 0, nodes: [], edges: [] });
    render(<KnowledgeGraph />);
    await screen.findByTestId("graph-node-insight-1");

    fireEvent.change(screen.getByLabelText("Search graph"), { target: { value: "missing" } });
    fireEvent.change(screen.getByLabelText("Node type"), { target: { value: "question" } });
    fireEvent.change(screen.getByLabelText("Graph scope"), { target: { value: "depth" } });
    fireEvent.change(screen.getByLabelText("Investigation id"), { target: { value: "inv-2" } });
    fireEvent.click(screen.getByText("Explore"));

    await waitFor(() =>
      expect(exploreGraph).toHaveBeenLastCalledWith({
        query: "missing",
        nodeType: "question",
        graphScope: "depth",
        investigationId: "inv-2",
      }),
    );
    expect(await screen.findByText(/Nothing in the graph matches/)).toBeTruthy();
    expect(screen.queryByTestId("graph-evidence-rail")).toBeNull();
  });
});
