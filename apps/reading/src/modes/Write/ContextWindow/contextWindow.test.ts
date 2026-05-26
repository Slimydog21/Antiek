import { describe, it, expect } from "vitest";

import type { ContextWindowState } from "./contextWindowState";
import { contextToPromoteRequest, generatability, itemToSpec } from "./contextWindowState";

/**
 * The pre-outline context window's pure core (SPR-08): state → promote
 * request (provenance preserved) + the no-blocks-no-fabrication gate.
 */

describe("itemToSpec — provenance preserved", () => {
  it("maps a node item to a graph_node spec carrying node_id", () => {
    const spec = itemToSpec({ label: "x", block_kind: "insight", node_id: "node-1" }, 0);
    expect(spec.provenance_kind).toBe("graph_node");
    expect(spec.node_id).toBe("node-1");
    expect(spec.content).toBeNull();
  });

  it("maps a user item to user_authored with content, never a node", () => {
    const spec = itemToSpec({ label: "y", block_kind: "user_authored", content: "mine" }, 1);
    expect(spec.provenance_kind).toBe("user_authored");
    expect(spec.node_id).toBeNull();
    expect(spec.content).toBe("mine");
  });
});

describe("contextToPromoteRequest", () => {
  it("builds a promote body and falls back the title to the objective", () => {
    const state: ContextWindowState = {
      title: "",
      objective: "argue that the edit is the writing",
      items: [{ label: "x", block_kind: "insight", node_id: "node-1" }],
    };
    const req = contextToPromoteRequest(state);
    expect(req.title).toBe("argue that the edit is the writing");
    expect(req.objective).toBe("argue that the edit is the writing");
    expect(req.blocks).toHaveLength(1);
    expect(req.blocks[0].node_id).toBe("node-1");
  });
});

describe("generatability — no-blocks-no-fabrication gate", () => {
  it("refuses to generate with no blocks (does not fabricate sources)", () => {
    const g = generatability({ title: "t", objective: "do a thing", items: [] });
    expect(g.ok).toBe(false);
    expect(g.reason.toLowerCase()).toContain("fabricate");
  });

  it("refuses with no objective", () => {
    const g = generatability({
      title: "t", objective: "  ",
      items: [{ label: "x", block_kind: "insight", node_id: "n" }],
    });
    expect(g.ok).toBe(false);
  });

  it("allows generation with blocks + objective", () => {
    const g = generatability({
      title: "t", objective: "argue X",
      items: [{ label: "x", block_kind: "insight", node_id: "n" }],
    });
    expect(g.ok).toBe(true);
  });
});
