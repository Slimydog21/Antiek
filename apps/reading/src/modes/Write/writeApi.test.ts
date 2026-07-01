import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", () => ({
  API_BASE: "/api",
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public readonly status: number,
      public readonly body: string,
    ) {
      super(message);
    }
  },
  apiFetch: apiFetchMock,
}));

import {
  blockDisplayText,
  emitBrainstormBlocks,
  generateSection,
  getTraceTarget,
  moveBlock,
  placeBlock,
  searchRepository,
} from "./writeApi";
import type { OutlineBlockView } from "./writeApi";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function postedJsonBody(callIndex = 0): Record<string, unknown> {
  const [, init] = apiFetchMock.mock.calls[callIndex] as [string, RequestInit];
  expect(typeof init.body).toBe("string");
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

beforeEach(() => {
  apiFetchMock.mockReset();
});

describe("writeApi client contracts", () => {
  it("searches repository with a relative API path and encoded filters", async () => {
    const hit = {
      node_id: "node-1",
      label: "Claim text",
      node_type: "claim",
      source_tier: 1,
      document_id: "doc-1",
      document_title: "Source",
      score: 0.9,
    };
    apiFetchMock.mockResolvedValueOnce(jsonResponse({ hits: [hit] }));

    const result = await searchRepository({
      q: "moral hazard",
      folderId: "folder/one",
      sourceDocumentId: "doc with space",
      limit: 5,
    });

    expect(apiFetchMock).toHaveBeenCalledWith(
      "/api/write/blocks/search?q=moral+hazard&folder_id=folder%2Fone&source_document_id=doc+with+space&limit=5",
    );
    expect(result).toEqual([hit]);
  });

  it("rejects malformed repository search limits before sending requests", async () => {
    await expect(searchRepository({ limit: 0 })).rejects.toThrow(/limit/);
    await expect(searchRepository({ limit: -1 })).rejects.toThrow(/limit/);
    await expect(searchRepository({ limit: 2.5 })).rejects.toThrow(/limit/);
    await expect(searchRepository({ limit: 9007199254740992 })).rejects.toThrow(/limit/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("places graph-node blocks without inline content and user-authored blocks without node ids", async () => {
    apiFetchMock.mockResolvedValueOnce(jsonResponse({ outline_block_id: "oblk-node" }));

    await expect(
      placeBlock({
        section_id: "sec-1",
        block_kind: "claim",
        provenance_kind: "graph_node",
        node_id: "node-claim",
        block_index: 2,
        deliverable_id: "deliv-1",
      }),
    ).resolves.toBe("oblk-node");
    expect(postedJsonBody()).toEqual({
      section_id: "sec-1",
      block_kind: "claim",
      provenance_kind: "graph_node",
      node_id: "node-claim",
      block_index: 2,
      deliverable_id: "deliv-1",
    });

    apiFetchMock.mockResolvedValueOnce(jsonResponse({ outline_block_id: "oblk-user" }));
    await expect(
      placeBlock({
        section_id: "sec-1",
        block_kind: "user_authored",
        provenance_kind: "user_authored",
        content: "my own paragraph seed",
        block_index: 3,
      }),
    ).resolves.toBe("oblk-user");
    expect(postedJsonBody(1)).toEqual({
      section_id: "sec-1",
      block_kind: "user_authored",
      provenance_kind: "user_authored",
      content: "my own paragraph seed",
      block_index: 3,
    });
  });

  it("rejects malformed write indices before sending requests", async () => {
    await expect(
      placeBlock({
        section_id: "sec-1",
        block_kind: "claim",
        provenance_kind: "graph_node",
        node_id: "node-claim",
        block_index: 1.5,
      }),
    ).rejects.toThrow(/block_index/);

    await expect(moveBlock("oblk-1", "sec-1", -1)).rejects.toThrow(/to_index/);
    await expect(
      generateSection("sec-1", { paragraphIndex: 9007199254740992 }),
    ).rejects.toThrow(/paragraph_index/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("keeps outline display text on content or node labels, never ids", () => {
    const base: OutlineBlockView = {
      outline_block_id: "oblk-secret",
      section_id: "sec-1",
      block_kind: "claim",
      provenance_kind: "graph_node",
      node_id: "node-secret",
      content: null,
      node_label: null,
      block_index: 0,
      is_user_originated: false,
    };

    expect(blockDisplayText({ ...base, content: "  user words  " })).toBe("user words");
    expect(blockDisplayText({ ...base, node_label: "  sourced claim  " })).toBe("sourced claim");
    expect(blockDisplayText(base)).toBe("(untitled block)");
  });

  it("generates whole sections without a body and paragraph repairs with a scoped body", async () => {
    apiFetchMock.mockResolvedValueOnce(jsonResponse({ status: "generated", section_id: "sec-1" }));
    await generateSection("sec 1");
    expect(apiFetchMock.mock.calls[0]).toEqual([
      "/api/write/sections/sec%201/generate",
      { method: "POST" },
    ]);

    apiFetchMock.mockResolvedValueOnce(jsonResponse({ status: "generated", section_id: "sec-1" }));
    await generateSection("sec 1", { paragraphIndex: 4 });
    const [, init] = apiFetchMock.mock.calls[1] as [string, RequestInit];
    expect(init).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(init.body as string)).toEqual({ paragraph_index: 4 });
  });

  it("emits brainstorm drivers as user-originated blocks through the write endpoint", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        block_ids: ["b1"],
        insight_count: 1,
        question_count: 1,
        data_count: 1,
        skipped_duplicates: 0,
        flagged_unverified: ["Revenue doubled"],
      }),
    );

    await emitBrainstormBlocks({
      section_id: "sec-1",
      deliverable_id: "deliv-1",
      insights: ["Insight"],
      questions: ["Question?"],
      data_points: ["Revenue doubled"],
    });

    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/write/brainstorm/emit-blocks");
    expect(postedJsonBody()).toEqual({
      section_id: "sec-1",
      deliverable_id: "deliv-1",
      insights: ["Insight"],
      questions: ["Question?"],
      data_points: ["Revenue doubled"],
    });
  });

  it("surfaces API failures as ApiError with status, body, and endpoint label", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("gate failed", { status: 403 }));

    await expect(getTraceTarget("oblk gated")).rejects.toMatchObject({
      message: "GET /write/blocks/{id}/trace failed: HTTP 403",
      status: 403,
      body: "gate failed",
    });
  });
});
