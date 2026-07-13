import { beforeEach, describe, expect, it, vi } from "vitest";

import { exploreGraph } from "./graph";

const apiFetch = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

describe("graph API", () => {
  beforeEach(() => apiFetch.mockReset());

  it("transports an exact encoded node id without degrading to q search", async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        query: "",
        node_id: "insight/a b",
        node_count: 0,
        edge_count: 0,
        truncated: false,
        read_only: true,
        view_format: "html",
        nodes: [],
        edges: [],
      }),
    });

    await exploreGraph({ nodeId: " insight/a b " });

    expect(apiFetch).toHaveBeenCalledWith(
      "/graph/explore?node_id=insight%2Fa+b&limit=60",
    );
    expect(apiFetch.mock.calls[0][0]).not.toContain("q=");
  });
});
