import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  attachBlock,
  appendNotebookBlock,
  createDeliverable,
  createSection,
  exportDeliverable,
  challengeNote,
  getAttributionReport,
  getChunk,
  getConsentView,
  getDistillation,
  getHealth,
  getDeliverable,
  getInvestigationStatus,
  getNotebook,
  getTrajectory,
  ingestSource,
  ingestVoiceNote,
  launchParkedQuestion,
  listDeliverables,
  listInvestigations,
  listWatchForLater,
  deleteNotebookBlock,
  patchNotebookBlock,
  postTypedEvent,
  reorderBlock,
  reorderNotebookBlocks,
  searchBlocks,
  transcribeAudio,
  undoAiAction,
  updateSectionProse,
} from "./api";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client numeric request bounds", () => {
  it("rejects malformed list/search limits before sending requests", async () => {
    await expect(getTrajectory("inv-1", 0)).rejects.toThrow(/limit/);
    await expect(listInvestigations({ limit: -1 })).rejects.toThrow(/limit/);
    await expect(listWatchForLater({ limit: 2.5 })).rejects.toThrow(/limit/);
    await expect(searchBlocks("claim", 9007199254740992)).rejects.toThrow(/limit/);

    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects malformed research read and challenge handles before sending requests", async () => {
    await expect(getTrajectory(" ")).rejects.toThrow(/investigationId/);
    await expect(getInvestigationStatus(" ")).rejects.toThrow(/investigationId/);
    await expect(getDistillation(" ")).rejects.toThrow(/investigationId/);
    await expect(challengeNote(" ", { investigation_id: "inv-1" })).rejects.toThrow(/nodeId/);
    await expect(challengeNote("node-1", { investigation_id: " " })).rejects.toThrow(
      /investigation_id/,
    );

    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects malformed section block indices before sending requests", async () => {
    await expect(
      attachBlock({
        section_id: "sec-1",
        block_kind: "claim",
        block_id: "blk-1",
        block_index: -1,
      }),
    ).rejects.toThrow(/block_index/);
    await expect(
      reorderBlock({
        section_id: "sec-1",
        block_kind: "claim",
        block_id: "blk-1",
        new_block_index: 1.5,
      }),
    ).rejects.toThrow(/new_block_index/);

    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects malformed write editor request handles before sending requests", async () => {
    await expect(createDeliverable({
      title: " ",
      deliverable_kind: "general_essay",
    })).rejects.toThrow(/title/);
    await expect(createSection({
      deliverable_id: "dlv-1",
      section_index: -1,
    })).rejects.toThrow(/section_index/);
    await expect(attachBlock({
      section_id: " ",
      block_kind: "claim",
      block_id: "blk-1",
      block_index: 0,
    })).rejects.toThrow(/section_id/);
    await expect(searchBlocks(" ")).rejects.toThrow(/q/);
    await expect(reorderBlock({
      section_id: "sec-1",
      block_kind: "claim",
      block_id: " ",
      new_block_index: 0,
    })).rejects.toThrow(/block_id/);
    await expect(updateSectionProse("sec-1", {
      prose_text: " ",
    })).rejects.toThrow(/prose_text/);
    await expect(exportDeliverable(" ", "markdown")).rejects.toThrow(/deliverable_id/);

    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("api client emitted-event response boundary", () => {
  it("sanitizes emitted event handles from typed-event and undo endpoints", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          event_id: " evt-applied ",
          action_type: " ai.action.applied ",
        }),
        { status: 200 },
      ),
    );

    await expect(
      postTypedEvent({
        investigation_id: "inv-1",
        payload: {
          action_type: "ai.action.applied",
          target_kind: "ui_layout",
          target_id: "panel-1",
          operator_prompt: "open panel",
          prev_state: {},
          next_state: { open: true },
          prev_state_hash: "hash",
          summary: "opened panel",
        },
      }),
    ).resolves.toEqual({
      event_id: "evt-applied",
      action_type: "ai.action.applied",
    });

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          event_id: " evt-undone ",
          action_type: " ai.action.undone ",
        }),
        { status: 200 },
      ),
    );

    await expect(
      undoAiAction({
        event_id: "evt-applied",
        investigation_id: "inv-1",
      }),
    ).resolves.toEqual({
      event_id: "evt-undone",
      action_type: "ai.action.undone",
    });
  });

  it("rejects malformed emitted event success responses", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ event_id: " ", action_type: "ai.action.applied" }), {
        status: 200,
      }),
    );

    await expect(
      postTypedEvent({
        investigation_id: "inv-1",
        payload: {
          action_type: "ai.action.applied",
          target_kind: "ui_layout",
          target_id: "panel-1",
          operator_prompt: "open panel",
          prev_state: {},
          next_state: { open: true },
          prev_state_hash: "hash",
          summary: "opened panel",
        },
      }),
    ).rejects.toMatchObject({ status: 502 });
  });
});

describe("api client health response boundary", () => {
  it("sanitizes provider activation health before feature gates read it", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: " ",
          param_version: " v1 ",
          schema_version: -1,
          subscriber_count: "not-a-number",
          registered_providers: [" openai ", "", 7, "anthropic"],
        }),
        { status: 200 },
      ),
    );

    await expect(getHealth()).resolves.toEqual({
      status: "unknown",
      param_version: "v1",
      schema_version: 0,
      subscriber_count: 0,
      registered_providers: ["openai", "anthropic"],
    });
  });
});

describe("api client investigation and watch-list response boundaries", () => {
  it("sanitizes trajectory event frames at the shared API boundary", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          investigation_id: " inv-1 ",
          count: "bad",
          events: [
            {
              event_id: "evt-valid",
              investigation_id: "inv-1",
              action_type: "dispatch.call",
              payload: { action_type: "dispatch.call", provider: "openai" },
              param_version: "v1",
              emitted_at: "2026-07-01T00:00:00Z",
            },
            {
              event_id: "evt-bad-action",
              investigation_id: "inv-1",
              action_type: "not.a.real.action",
              payload: { action_type: "not.a.real.action" },
              param_version: "v1",
              emitted_at: "2026-07-01T00:00:01Z",
            },
            {
              event_id: "evt-mismatch",
              investigation_id: "inv-1",
              action_type: "dispatch.call",
              payload: { action_type: "phase.enter" },
              param_version: "v1",
              emitted_at: "2026-07-01T00:00:02Z",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(getTrajectory("fallback-inv")).resolves.toMatchObject({
      investigation_id: "inv-1",
      count: 1,
      events: [
        {
          event_id: "evt-valid",
          action_type: "dispatch.call",
        },
      ],
    });
  });

  it("trims research read handles before constructing request URLs", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ investigation_id: " ", count: 0, events: [] }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ investigation_id: " ", status: "completed" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ investigation_id: " ", insights: [], questions: [] }),
          { status: 200 },
        ),
      );

    await expect(getTrajectory(" inv dirty/1 ", 2)).resolves.toMatchObject({
      investigation_id: "inv dirty/1",
    });
    await expect(getInvestigationStatus(" inv dirty/1 ")).resolves.toMatchObject({
      investigation_id: "inv dirty/1",
    });
    await expect(getDistillation(" inv dirty/1 ")).resolves.toMatchObject({
      investigation_id: "inv dirty/1",
    });

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      new URL("/trajectory/inv%20dirty%2F1?limit=2", window.location.origin).toString(),
      expect.any(Object),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/investigations/inv%20dirty%2F1",
      expect.any(Object),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "/research/inv%20dirty%2F1/distill",
      expect.any(Object),
    );
  });

  it("sanitizes investigation list rows before sidebar consumers render them", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          count: "not-a-number",
          investigations: [
            {
              investigation_id: " inv-1 ",
              question: "  What happened?  ",
              status: "completed",
              started_at: " 2026-07-01T00:00:00Z ",
              completed_at: " ",
              cost_usd_total: "1.25",
              parent_investigation_id: " parent-1 ",
              spawned_by_daemon: true,
            },
            {
              investigation_id: "inv-2",
              question: " ",
              status: "mystery",
              cost_usd_total: -1,
            },
            {
              investigation_id: " ",
              question: "skip me",
              status: "completed",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(listInvestigations()).resolves.toEqual({
      count: 2,
      investigations: [
        {
          investigation_id: "inv-1",
          question: "What happened?",
          status: "completed",
          started_at: "2026-07-01T00:00:00Z",
          completed_at: null,
          cost_usd_total: 1.25,
          parent_investigation_id: "parent-1",
          spawned_by_daemon: true,
        },
        {
          investigation_id: "inv-2",
          question: null,
          status: "failed",
          started_at: null,
          completed_at: null,
          cost_usd_total: 0,
          parent_investigation_id: null,
        },
      ],
    });
  });

  it("sanitizes investigation status responses before terminal surfaces render them", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          investigation_id: " ",
          status: "stopped",
          current_phase: "2",
          last_delivered_action_type: " synthesis.completed ",
          terminal_payload: [],
          rubric_score: {
            composite: "1.7",
            voice_style: -1,
            conviction: 0.5,
            citation_density: "0.4",
            constraint_compliance: Number.POSITIVE_INFINITY,
            notes: "  Solid answer  ",
          },
        }),
        { status: 200 },
      ),
    );

    await expect(getInvestigationStatus("fallback-inv")).resolves.toEqual({
      investigation_id: "fallback-inv",
      status: "failed",
      current_phase: null,
      last_delivered_action_type: "synthesis.completed",
      terminal_payload: null,
      rubric_score: {
        composite: 1,
        voice_style: null,
        conviction: 0.5,
        citation_density: 0.4,
        constraint_compliance: null,
        notes: "Solid answer",
      },
    });
  });

  it("sanitizes watch-for-later rows and supports the legacy parked key", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          parked: [
            {
              question_id: " q-1 ",
              question_text: "  Chase this  ",
              source_investigation_id: " inv-1 ",
              source_document_id: " ",
              anchor_region_id: " region-1 ",
              parked_at: " 2026-07-01T00:00:00Z ",
              parent_event_id: null,
            },
            {
              question_id: "q-bad",
              question_text: " ",
              source_investigation_id: "inv-1",
              parked_at: "2026-07-01T00:00:00Z",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(listWatchForLater()).resolves.toEqual({
      count: 1,
      questions: [
        {
          question_id: "q-1",
          question_text: "Chase this",
          source_investigation_id: "inv-1",
          source_document_id: null,
          anchor_region_id: "region-1",
          parked_at: "2026-07-01T00:00:00Z",
          parent_event_id: null,
        },
      ],
    });
  });

  it("rejects parked-question launch responses without usable handles", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          investigation_id: " inv-new ",
          status: " ",
          start_event_id: " evt-start ",
        }),
        { status: 200 },
      ),
    );

    await expect(launchParkedQuestion(" q dirty/1 ")).resolves.toEqual({
      investigation_id: "inv-new",
      status: "in_progress",
      start_event_id: "evt-start",
    });
    expect(fetch).toHaveBeenCalledWith(
      "/watch-for-later/q%20dirty%2F1/launch",
      expect.objectContaining({ method: "POST" }),
    );

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          investigation_id: " ",
          status: "in_progress",
          start_event_id: "evt-start",
        }),
        { status: 200 },
      ),
    );

    await expect(launchParkedQuestion("q-2")).rejects.toMatchObject({
      status: 502,
    });
  });

  it("rejects blank parked-question launch handles before network", async () => {
    await expect(launchParkedQuestion(" ")).rejects.toThrow(
      "question_id must be a non-empty string",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("api client write deliverable response boundaries", () => {
  it("sanitizes deliverable lists before Write renders project state", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          count: "bad",
          deliverables: [
            {
              deliverable_id: " dlv-1 ",
              title: "  Essay draft  ",
              deliverable_kind: "not-a-kind",
              investigation_root_id: " inv-root ",
              status: " generated ",
              created_at: " 2026-07-01T00:00:00Z ",
              updated_at: " ",
              section_count: "2",
            },
            {
              deliverable_id: " ",
              title: "Invisible",
              deliverable_kind: "research_memo",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(listDeliverables()).resolves.toEqual({
      count: 1,
      deliverables: [
        {
          deliverable_id: "dlv-1",
          title: "Essay draft",
          deliverable_kind: "general_essay",
          investigation_root_id: "inv-root",
          status: "generated",
          created_at: "2026-07-01T00:00:00Z",
          updated_at: null,
          section_count: 0,
        },
      ],
    });
  });

  it("sanitizes deliverable details and section provenance for the outline", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          deliverable_id: " dlv-1 ",
          title: "  Essay draft  ",
          deliverable_kind: "book_chapter",
          investigation_root_id: " ",
          status: " active ",
          sections: [
            {
              section_id: " sec-1 ",
              deliverable_id: " dlv-1 ",
              parent_section_id: " parent-1 ",
              section_index: "1",
              title: "  Opening  ",
              prose_text: "  Draft prose  ",
              prose_provenance: {
                " 0 ": [" block-1 ", "", 7],
                "1": "block-2",
                " ": ["block-hidden"],
              },
              block_count: "3",
            },
            {
              section_id: "",
              deliverable_id: "dlv-1",
              title: "Invisible",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(getDeliverable("dlv-1")).resolves.toEqual({
      deliverable_id: "dlv-1",
      title: "Essay draft",
      deliverable_kind: "book_chapter",
      status: "active",
      investigation_root_id: null,
      sections: [
        {
          section_id: "sec-1",
          deliverable_id: "dlv-1",
          parent_section_id: "parent-1",
          section_index: 0,
          title: "Opening",
          prose_text: "Draft prose",
          prose_provenance: { "0": ["block-1"] },
          block_count: 0,
        },
      ],
    });
  });

  it("rejects malformed created deliverables instead of navigating to dead routes", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ deliverable_id: " ", title: "Bad" }), {
        status: 200,
      }),
    );

    await expect(
      createDeliverable({
        title: "Bad",
        deliverable_kind: "general_essay",
      }),
    ).rejects.toMatchObject({ status: 502 });
  });

  it("sanitizes created sections before outline state receives them", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          section_id: " sec-2 ",
          deliverable_id: " dlv-1 ",
          section_index: 2,
          title: "  Second  ",
          prose_text: null,
          prose_provenance: [],
          block_count: 1,
        }),
        { status: 200 },
      ),
    );

    await expect(
      createSection({
        deliverable_id: "dlv-1",
        section_index: 2,
        title: "Second",
      }),
    ).resolves.toEqual({
      section_id: "sec-2",
      deliverable_id: "dlv-1",
      parent_section_id: null,
      section_index: 2,
      title: "Second",
      prose_text: null,
      prose_provenance: null,
      block_count: 1,
    });
  });
});

describe("api client write editor response boundaries", () => {
  it("sanitizes block search hits before the repository picker renders them", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          count: "bad",
          hits: [
            {
              block_id: " blk-1 ",
              block_kind: "mystery",
              label: " ",
              body: "  The useful claim  ",
              source_tier: "2",
              document_title: "  Source doc  ",
            },
            {
              block_id: "blk-empty",
              body: " ",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(searchBlocks(" claim ", 5)).resolves.toEqual({
      count: 1,
      hits: [
        {
          block_id: "blk-1",
          block_kind: "claim",
          label: "The useful claim",
          body: "The useful claim",
          source_tier: null,
          document_title: "Source doc",
        },
      ],
    });
    const url = new URL(vi.mocked(fetch).mock.calls[0][0] as string);
    expect(url.pathname).toBe("/blocks/search");
    expect(url.searchParams.get("q")).toBe("claim");
    expect(url.searchParams.get("limit")).toBe("5");
  });

  it("sanitizes deliverable and section request bodies before write assembly", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            deliverable_id: " dlv-1 ",
            title: "Draft",
            deliverable_kind: "research_memo",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            section_id: " sec-1 ",
            deliverable_id: " dlv-1 ",
            section_index: 0,
          }),
          { status: 200 },
        ),
      );

    await expect(createDeliverable({
      title: " Draft ",
      deliverable_kind: " research_memo " as never,
      investigation_root_id: " inv-root ",
    })).resolves.toMatchObject({ deliverable_id: "dlv-1" });
    await expect(createSection({
      deliverable_id: " dlv-1 ",
      section_index: 0,
      title: " Intro ",
      parent_section_id: " ",
    })).resolves.toMatchObject({ section_id: "sec-1" });

    const createDeliverableCall = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(createDeliverableCall[1].body as string)).toEqual({
      title: "Draft",
      deliverable_kind: "research_memo",
      investigation_root_id: "inv-root",
    });
    const createSectionCall = vi.mocked(fetch).mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(createSectionCall[1].body as string)).toEqual({
      deliverable_id: "dlv-1",
      section_index: 0,
      title: "Intro",
    });
  });

  it("sanitizes section block attach and reorder request bodies", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(attachBlock({
      section_id: " sec-1 ",
      block_kind: " claim " as never,
      block_id: " block-1 ",
      block_index: 0,
    })).resolves.toBeUndefined();
    await expect(reorderBlock({
      section_id: " sec-1 ",
      block_kind: " claim " as never,
      block_id: " block-1 ",
      new_section_id: " sec-2 ",
      new_block_index: 1,
    })).resolves.toBeUndefined();

    const attachCall = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(attachCall[1].body as string)).toEqual({
      section_id: "sec-1",
      block_kind: "claim",
      block_id: "block-1",
      block_index: 0,
    });
    const reorderCall = vi.mocked(fetch).mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(reorderCall[1].body as string)).toEqual({
      section_id: "sec-1",
      block_kind: "claim",
      block_id: "block-1",
      new_section_id: "sec-2",
      new_block_index: 1,
    });
  });

  it("sanitizes section prose save responses before editor state receives them", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: "unexpected",
          section_id: " sec-1 ",
          claim_node_id: " ",
          claim_event_id: " evt-1 ",
        }),
        { status: 200 },
      ),
    );

    await expect(
      updateSectionProse(" sec dirty/1 ", {
        prose_text: " Draft ",
        original_text: " Original ",
        promote_to_graph: true,
        cited_chunk_ids: [" chunk-1 "],
        investigation_id: " inv-1 ",
      }),
    ).resolves.toEqual({
      status: "saved",
      section_id: "sec-1",
      claim_node_id: null,
      claim_event_id: "evt-1",
    });
    const call = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(call[0]).toBe("/sections/sec%20dirty%2F1/prose");
    expect(JSON.parse(call[1].body as string)).toEqual({
      prose_text: "Draft",
      original_text: "Original",
      promote_to_graph: true,
      cited_chunk_ids: ["chunk-1"],
      investigation_id: "inv-1",
    });
  });

  it("rejects malformed section prose save responses", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "saved", section_id: " " }), {
        status: 200,
      }),
    );

    await expect(
      updateSectionProse("sec-1", {
        prose_text: "Draft",
      }),
    ).rejects.toMatchObject({ status: 502 });
  });

  it("sanitizes export responses before download code consumes them", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          format: "docx",
          content: "# Draft",
          filename: " ",
          content_encoding: "binary",
        }),
        { status: 200 },
      ),
    );

    await expect(exportDeliverable(" dlv dirty/1 ", " markdown " as never)).resolves.toEqual({
      format: "markdown",
      content: "# Draft",
      filename: "deliverable.markdown",
      content_encoding: "text",
    });
    const url = new URL(vi.mocked(fetch).mock.calls[0][0] as string);
    expect(url.pathname).toBe("/deliverables/dlv%20dirty%2F1/export");
    expect(url.searchParams.get("format")).toBe("markdown");
  });

  it("rejects malformed export content", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ format: "markdown", content: null }), {
        status: 200,
      }),
    );

    await expect(exportDeliverable("dlv-1", "markdown")).rejects.toMatchObject({
      status: 502,
    });
  });
});

describe("api client notebook response boundary", () => {
  it("sanitizes notebook responses before rendering blocks", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          notebook_id: " nb-1 ",
          title: " ",
          investigation_id: " inv-1 ",
          document_id: " ",
          content_class: "surprise",
          created_at: " 2026-07-01T00:00:00Z ",
          updated_at: " ",
          blocks: [
            {
              block_id: " blk-1 ",
              block_index: 0,
              block_type: " prose ",
              ref_id: " ",
              content_json: { text: "Hello" },
              created_at: " 2026-07-01T00:01:00Z ",
            },
            {
              block_id: "blk-bad-type",
              block_index: 1,
              block_type: "unknown",
              content_json: { text: "Skip" },
            },
            {
              block_id: "",
              block_index: 2,
              block_type: "note",
              content_json: { text: "Skip" },
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(getNotebook(" nb dirty/1 ")).resolves.toEqual({
      notebook_id: "nb-1",
      title: "nb-1",
      investigation_id: "inv-1",
      document_id: null,
      content_class: "user_owned",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "",
      blocks: [
        {
          block_id: "blk-1",
          block_index: 0,
          block_type: "prose",
          ref_id: null,
          content_json: { text: "Hello" },
          created_at: "2026-07-01T00:01:00Z",
        },
      ],
    });
    expect(fetch).toHaveBeenCalledWith(
      "/notebooks/nb%20dirty%2F1",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("rejects notebook responses without a usable notebook id", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ notebook_id: " ", blocks: [] }), {
        status: 200,
      }),
    );

    await expect(getNotebook("nb-1")).rejects.toMatchObject({ status: 502 });
  });

  it("sanitizes append notebook responses through the same boundary", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          notebook_id: " nb-append ",
          title: "Append",
          content_class: "user_public_contribution",
          blocks: [
            {
              block_id: " block-1 ",
              block_index: 0,
              block_type: "note",
              ref_id: " note-1 ",
              content_json: [],
              created_at: null,
            },
          ],
        }),
        { status: 200 },
      ),
    );

    const result = await appendNotebookBlock(" nb-append ", {
      block_type: " note ",
      content: { text: "x" },
      ref_id: " note-ref ",
    });

    expect(result.notebook_id).toBe("nb-append");
    expect(result.content_class).toBe("user_public_contribution");
    expect(result.blocks).toEqual([
      {
        block_id: "block-1",
        block_index: 0,
        block_type: "note",
        ref_id: "note-1",
        content_json: {},
        created_at: "",
      },
    ]);
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(fetch).toHaveBeenCalledWith(
      "/notebooks/nb-append/blocks",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(init.body as string)).toEqual({
      block_type: "note",
      content: { text: "x" },
      ref_id: "note-ref",
    });
  });

  it("sanitizes notebook edit, delete, and reorder request handles", async () => {
    const ok = () =>
      new Response(JSON.stringify({ notebook_id: " nb-1 ", blocks: [] }), {
        status: 200,
      });
    vi.mocked(fetch)
      .mockResolvedValueOnce(ok())
      .mockResolvedValueOnce(ok())
      .mockResolvedValueOnce(ok());

    await expect(patchNotebookBlock(" nb dirty/1 ", " block dirty/1 ", {
      content: { text: "edited" },
      ref_id: " ref-1 ",
    })).resolves.toMatchObject({ notebook_id: "nb-1" });
    await expect(deleteNotebookBlock(" nb dirty/1 ", " block dirty/2 ")).resolves.toMatchObject({
      notebook_id: "nb-1",
    });
    await expect(reorderNotebookBlocks(" nb dirty/1 ", [
      " block-2 ",
      " block-1 ",
    ])).resolves.toMatchObject({ notebook_id: "nb-1" });

    const patchCall = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(patchCall[0]).toBe("/notebooks/nb%20dirty%2F1/blocks/block%20dirty%2F1");
    expect(JSON.parse(patchCall[1].body as string)).toEqual({
      content: { text: "edited" },
      ref_id: "ref-1",
    });
    expect(vi.mocked(fetch).mock.calls[1][0]).toBe(
      "/notebooks/nb%20dirty%2F1/blocks/block%20dirty%2F2",
    );
    const reorderCall = vi.mocked(fetch).mock.calls[2] as [string, RequestInit];
    expect(reorderCall[0]).toBe("/notebooks/nb%20dirty%2F1/blocks/reorder");
    expect(JSON.parse(reorderCall[1].body as string)).toEqual({
      ordered_block_ids: ["block-2", "block-1"],
    });
  });

  it("rejects malformed notebook request handles before network", async () => {
    await expect(getNotebook(" ")).rejects.toThrow("notebookId must be a non-empty string");
    await expect(appendNotebookBlock("nb-1", {
      block_type: "unknown",
      content: {},
    })).rejects.toThrow("block_type must be a supported notebook block type");
    await expect(patchNotebookBlock("nb-1", " ", { content: {} })).rejects.toThrow(
      "blockId must be a non-empty string",
    );
    await expect(deleteNotebookBlock(" ", "block-1")).rejects.toThrow(
      "notebookId must be a non-empty string",
    );
    await expect(reorderNotebookBlocks("nb-1", ["block-1", " block-1 "])).rejects.toThrow(
      "ordered_block_ids must not contain duplicates",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("api client research graph response boundaries", () => {
  it("sanitizes voice-note, transcription, and source ingest responses", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: "surprise",
          document_id: " doc-voice ",
          document_loaded_event_id: " ",
          chunks_written: "3",
          skipped_reason: null,
          title: "  Voice memo  ",
        }),
        { status: 200 },
      ),
    );

    await expect(
      ingestVoiceNote({ transcript: "captured idea" }),
    ).resolves.toEqual({
      status: "ingested",
      document_id: "doc-voice",
      document_loaded_event_id: null,
      chunks_written: 0,
      skipped_reason: null,
      title: "Voice memo",
    });

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          transcript: "  captured idea  ",
          language: " en ",
          duration_seconds: "12",
        }),
        { status: 200 },
      ),
    );

    await expect(transcribeAudio(new Blob(["audio"]))).resolves.toEqual({
      transcript: "captured idea",
      language: "en",
      duration_seconds: 12,
    });

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: "error",
          detected_kind: " ",
          document_id: " doc-source ",
          document_loaded_event_id: " ev-source ",
          chunks_written: 4,
          skipped_reason: " ",
          error_message: "  parse failed  ",
          title: "  Source title  ",
          episodes_processed: "2",
          episodes_ingested: 1,
        }),
        { status: 200 },
      ),
    );

    await expect(ingestSource({ url: "https://example.test" })).resolves.toEqual({
      status: "error",
      detected_kind: "url",
      document_id: "doc-source",
      document_loaded_event_id: "ev-source",
      chunks_written: 4,
      skipped_reason: null,
      error_message: "parse failed",
      title: "Source title",
      episodes_processed: 0,
      episodes_ingested: 1,
    });
  });

  it("rejects malformed voice-note and transcription success responses", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ingested", document_id: " " }), {
        status: 200,
      }),
    );

    await expect(ingestVoiceNote({ transcript: "x" })).rejects.toMatchObject({
      status: 502,
    });

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ transcript: null }), { status: 200 }),
    );

    await expect(transcribeAudio(new Blob(["audio"]))).rejects.toMatchObject({
      status: 502,
    });
  });

  it("sanitizes distillation and challenge-note responses before graph state receives them", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          investigation_id: " ",
          insights: [
            {
              node_id: " node-1 ",
              kind: "surprise",
              text: "  Useful finding  ",
              confidence: " high ",
              source_document_id: " doc-1 ",
              chunk_id: " ",
              refinement_count: "2",
              escalated: "yes",
            },
            {
              node_id: "node-empty",
              text: " ",
            },
          ],
          questions: [
            {
              node_id: " q-1 ",
              text: "  What next?  ",
              reserved_child_investigation_id: " child-1 ",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(getDistillation("inv-fallback")).resolves.toEqual({
      investigation_id: "inv-fallback",
      insights: [
        {
          node_id: "node-1",
          kind: "surprise",
          text: "Useful finding",
          confidence: "high",
          source_document_id: "doc-1",
          chunk_id: null,
          refinement_count: 0,
          escalated: false,
          reserved_child_investigation_id: null,
        },
      ],
      questions: [
        {
          node_id: "q-1",
          kind: "question",
          text: "What next?",
          confidence: null,
          source_document_id: null,
          chunk_id: null,
          refinement_count: 0,
          escalated: false,
          reserved_child_investigation_id: "child-1",
        },
      ],
    });

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          node_id: " node-1 ",
          applied: "yes",
          superseded: true,
          new_text: " ",
          escalated: true,
          reserved_child_investigation_id: " child-2 ",
        }),
        { status: 200 },
      ),
    );

    await expect(
      challengeNote("node-1", { investigation_id: "inv-1" }),
    ).resolves.toEqual({
      node_id: "node-1",
      applied: false,
      superseded: true,
      new_text: null,
      escalated: true,
      reserved_child_investigation_id: "child-2",
    });
  });

  it("rejects malformed challenge-note handles", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ node_id: " ", applied: true }), {
        status: 200,
      }),
    );

    await expect(
      challengeNote("node-1", { investigation_id: "inv-1" }),
    ).rejects.toMatchObject({ status: 502 });
  });

  it("trims challenge-note request handles and body text before sending", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ node_id: " node-1 ", applied: true }), { status: 200 }),
    );

    await expect(
      challengeNote(" node dirty/1 ", {
        investigation_id: " inv dirty/1 ",
        challenge_text: "  sharpen this  ",
      }),
    ).resolves.toMatchObject({
      node_id: "node-1",
      applied: true,
    });

    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/research/notes/node%20dirty%2F1/challenge");
    expect(JSON.parse(init.body as string)).toEqual({
      investigation_id: "inv dirty/1",
      challenge_text: "sharpen this",
    });
  });

  it("sanitizes chunk responses without widening servability metadata", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          chunk_id: " ",
          text: 7,
          section_path: " p.12 ",
          token_count: "12",
          document_id: " doc-1 ",
          document_title: "  Source doc  ",
          source_tier: "2",
          servable: false,
          ip_holder_name: "  Hidden owner  ",
          ip_holder_status: "claimed",
          servability: " restricted ",
        }),
        { status: 200 },
      ),
    );

    await expect(getChunk("chunk-fallback")).resolves.toEqual({
      chunk_id: "chunk-fallback",
      text: "",
      section_path: "p.12",
      token_count: 0,
      document_id: "doc-1",
      document_title: "Source doc",
      source_tier: 0,
      servable: false,
      ip_holder_name: null,
      ip_holder_status: null,
      servability: "restricted",
    });
  });

  it("rejects chunk responses without a document handle", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ chunk_id: "chunk-1", document_id: " " }), {
        status: 200,
      }),
    );

    await expect(getChunk("chunk-1")).rejects.toMatchObject({ status: 502 });
  });
});

describe("api client attribution and consent response boundaries", () => {
  it("sanitizes attribution reports before economics surfaces render shares", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          synthesis_id: " ",
          target_question: "  Who gets credit?  ",
          option_a: {
            algorithm: "Z",
            shares: {
              " doc-1 ": "0.6",
              " ": 0.4,
              "doc-bad": -1,
            },
            document_titles: {
              " doc-1 ": "  Source one  ",
              "doc-empty": " ",
            },
            document_count: "2",
            claim_count: 3,
            document_ip_holders: {
              " doc-1 ": " rights-1 ",
              "doc-2": " ",
            },
            document_ip_holder_status: {
              " rights-1 ": " claimed ",
              " ": "hidden",
            },
          },
          option_b: null,
          option_c: {
            algorithm: "C",
            shares: { "doc-3": 0.25 },
          },
        }),
        { status: 200 },
      ),
    );

    await expect(getAttributionReport("syn-fallback")).resolves.toEqual({
      synthesis_id: "syn-fallback",
      target_question: "Who gets credit?",
      option_a: {
        algorithm: "A",
        shares: { "doc-1": 0.6 },
        document_titles: { "doc-1": "Source one" },
        document_count: 0,
        claim_count: 3,
        document_ip_holders: { "doc-1": "rights-1", "doc-2": null },
        document_ip_holder_status: { "rights-1": "claimed" },
      },
      option_b: {
        algorithm: "B",
        shares: {},
        document_titles: {},
        document_count: 0,
        claim_count: 0,
        document_ip_holders: {},
        document_ip_holder_status: {},
      },
      option_c: {
        algorithm: "C",
        shares: { "doc-3": 0.25 },
        document_titles: {},
        document_count: 0,
        claim_count: 0,
        document_ip_holders: {},
        document_ip_holder_status: {},
      },
    });
  });

  it("sanitizes consent and escrow views with disbursement deny-by-default", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          holders: [
            {
              ip_holder_id: " rights-1 ",
              display_name: "  Publisher One  ",
              status: " claimed ",
              escrow_balance_usd: " 12.50 ",
              gate: {
                disbursable: "yes",
                open_gate_ids: [" G2 ", "", 7, "G3"],
                holder_claimed: true,
                fully_unlocked: "yes",
                label: " ",
              },
              serves_full_text: "true",
              servability_note: "  opt-in pending  ",
            },
            {
              ip_holder_id: " ",
              display_name: "Invisible",
            },
          ],
          escrow_report: {
            pre_onboarded: "2",
            invited: 1,
            claimed: -1,
            opted_out: 0,
            claim_rate: "0.5",
            total_escrow_accrued_cents: "1250",
            total_escrow_paid_cents: 100,
            unclaimed_escrow_cents: Number.POSITIVE_INFINITY,
            publishers_with_nontrivial_accrual: 1,
          },
          disbursement_gates_open: [" G2 ", null, "G3"],
          total_escrow_accruing_usd: " 12.50 ",
          any_disbursable: "yes",
          gate_source_path: "  /config/gates  ",
        }),
        { status: 200 },
      ),
    );

    await expect(getConsentView()).resolves.toEqual({
      holders: [
        {
          ip_holder_id: "rights-1",
          display_name: "Publisher One",
          status: "claimed",
          escrow_balance_usd: "12.50",
          gate: {
            disbursable: false,
            open_gate_ids: ["G2", "G3"],
            holder_claimed: true,
            fully_unlocked: false,
            label: "gated",
          },
          serves_full_text: null,
          servability_note: "opt-in pending",
        },
      ],
      escrow_report: {
        pre_onboarded: 0,
        invited: 1,
        claimed: 0,
        opted_out: 0,
        claim_rate: 0.5,
        total_escrow_accrued_cents: 0,
        total_escrow_paid_cents: 100,
        unclaimed_escrow_cents: 0,
        publishers_with_nontrivial_accrual: 1,
      },
      disbursement_gates_open: ["G2", "G3"],
      total_escrow_accruing_usd: "12.50",
      any_disbursable: false,
      gate_source_path: "/config/gates",
    });
  });
});
