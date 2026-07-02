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
  createFolder,
  emitBrainstormBlocks,
  generateSection,
  getSectionBlocks,
  getTraceTarget,
  listFolders,
  moveBlock,
  placeBlock,
  promoteContext,
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

  it("sanitizes repository search results before they become outline sources", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        hits: [
          {
            node_id: " node-1 ",
            label: "  Claim text  ",
            node_type: "",
            source_tier: "2",
            document_id: " doc-1 ",
            document_title: "  Source  ",
            score: "0.7",
          },
          {
            node_id: "",
            label: "Missing node id",
            node_type: "claim",
            score: 0.4,
          },
        ],
      }),
    );

    await expect(searchRepository({ q: "hazard" })).resolves.toEqual([
      {
        node_id: "node-1",
        label: "Claim text",
        node_type: "insight",
        source_tier: 2,
        document_id: "doc-1",
        document_title: "Source",
        score: 0.7,
      },
    ]);
  });

  it("sanitizes write folders and section blocks from API responses", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        folders: [
          { folder_id: " folder-1 ", name: "  Saved  ", member_count: "3" },
          { folder_id: " ", name: "Skipped", member_count: 1 },
        ],
      }),
    );

    await expect(listFolders()).resolves.toEqual([
      { folder_id: "folder-1", name: "Saved", member_count: 3 },
    ]);

    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        blocks: [
          {
            outline_block_id: " oblk-1 ",
            section_id: " sec-1 ",
            block_kind: "",
            provenance_kind: "",
            node_id: " node-1 ",
            content: " ",
            node_label: "  Claim label  ",
            block_index: "4",
            is_user_originated: "yes",
          },
          {
            outline_block_id: "",
            section_id: "sec-1",
            block_index: 0,
          },
        ],
      }),
    );

    await expect(getSectionBlocks("sec-1")).resolves.toEqual([
      {
        outline_block_id: "oblk-1",
        section_id: "sec-1",
        block_kind: "insight",
        provenance_kind: "graph_node",
        node_id: "node-1",
        content: null,
        node_label: "Claim label",
        block_index: 4,
        is_user_originated: false,
      },
    ]);
  });

  it("places graph-node blocks without inline content and user-authored blocks without node ids", async () => {
    apiFetchMock.mockResolvedValueOnce(jsonResponse({ outline_block_id: " oblk-node " }));

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

  it("rejects malformed id responses from write mutations", async () => {
    apiFetchMock.mockResolvedValueOnce(jsonResponse({ outline_block_id: " " }));
    await expect(
      placeBlock({
        section_id: "sec-1",
        block_kind: "claim",
        provenance_kind: "graph_node",
        node_id: "node-claim",
        block_index: 0,
      }),
    ).rejects.toThrow(/outline_block_id/);

    apiFetchMock.mockResolvedValueOnce(jsonResponse({ folder_id: "" }));
    await expect(createFolder("Saved insights")).rejects.toThrow(/folder_id/);
  });

  it("trims folder ids returned from createFolder", async () => {
    apiFetchMock.mockResolvedValueOnce(jsonResponse({ folder_id: " folder-1 " }));

    await expect(createFolder("Saved insights")).resolves.toBe("folder-1");
    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/write/folders");
    expect(postedJsonBody()).toEqual({ name: "Saved insights" });
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
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        status: "generated",
        section_id: " sec-1 ",
        prose_text: "  Draft paragraph.  ",
        unsupported_paragraphs: ["0", 1.5, 2],
        fabricated_citations: [" c1 ", ""],
        prose_provenance: { " 0 ": [" oblk-1 ", "", 7] },
      }),
    );
    await expect(generateSection("sec 1")).resolves.toEqual({
      status: "generated",
      section_id: "sec-1",
      prose_text: "Draft paragraph.",
      detail: undefined,
      gate_passed: null,
      all_claims_cited: null,
      unsupported_paragraphs: [0, 2],
      fabricated_citations: ["c1"],
      prose_provenance: { "0": ["oblk-1"] },
    });
    expect(apiFetchMock.mock.calls[0]).toEqual([
      "/api/write/sections/sec%201/generate",
      { method: "POST" },
    ]);

    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({ status: "unexpected", section_id: "", detail: "  model branch  " }),
    );
    await expect(generateSection("sec 1", { paragraphIndex: 4 })).resolves.toMatchObject({
      status: "invalid",
      section_id: "sec 1",
      detail: "model branch",
    });
    const [, init] = apiFetchMock.mock.calls[1] as [string, RequestInit];
    expect(init).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(init.body as string)).toEqual({ paragraph_index: 4 });
  });

  it("sanitizes trace and promotion responses at the write API boundary", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        kind: "",
        full_text_allowed: true,
        document_id: " doc-1 ",
        document_title: "  Source Book  ",
        chunk_ids: [" c1 ", "", 9],
        primary_chunk_index: "2",
        primary_section_path: "  Page 3  ",
        servability_status: " servable ",
        detail: " ",
      }),
    );

    await expect(getTraceTarget("oblk-1")).resolves.toEqual({
      kind: "unknown",
      full_text_allowed: true,
      document_id: "doc-1",
      document_title: "Source Book",
      chunk_ids: ["c1"],
      primary_chunk_index: 2,
      primary_section_path: "Page 3",
      servability_status: "servable",
      detail: null,
    });

    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        deliverable_id: " dlv-1 ",
        section_id: " sec-1 ",
        block_ids: [" oblk-1 ", "", 7],
      }),
    );

    await expect(promoteContext({ objective: "draft" })).resolves.toEqual({
      deliverable_id: "dlv-1",
      section_id: "sec-1",
      block_ids: ["oblk-1"],
    });
  });

  it("masks gated trace locators in the write API client", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        kind: "document",
        full_text_allowed: false,
        document_id: "doc-gated",
        document_title: "Gated Book",
        chunk_ids: ["secret-chunk"],
        primary_chunk_index: 8,
        primary_section_path: "Restricted appendix",
        servability_status: " restricted_pending_opt_in ",
        detail: "  gated source  ",
      }),
    );

    await expect(getTraceTarget("oblk-gated")).resolves.toEqual({
      kind: "document",
      full_text_allowed: false,
      document_id: null,
      document_title: null,
      chunk_ids: [],
      primary_chunk_index: null,
      primary_section_path: null,
      servability_status: "restricted_pending_opt_in",
      detail: "gated source",
    });
  });

  it("rejects malformed promotion handles instead of producing stray drafts", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({ deliverable_id: "dlv-1", section_id: " " }),
    );

    await expect(promoteContext({ objective: "draft" })).rejects.toThrow(
      "Malformed write promotion response.",
    );
  });

  it("emits brainstorm drivers as user-originated blocks through the write endpoint", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        block_ids: [" b1 ", "", 5],
        insight_count: "1",
        question_count: 1,
        data_count: 1.5,
        skipped_duplicates: -1,
        flagged_unverified: [" Revenue doubled ", ""],
      }),
    );

    await expect(emitBrainstormBlocks({
      section_id: "sec-1",
      deliverable_id: "deliv-1",
      insights: ["Insight"],
      questions: ["Question?"],
      data_points: ["Revenue doubled"],
    })).resolves.toEqual({
      block_ids: ["b1"],
      insight_count: 1,
      question_count: 1,
      data_count: 0,
      skipped_duplicates: 0,
      flagged_unverified: ["Revenue doubled"],
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
