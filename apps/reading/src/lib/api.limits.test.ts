import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  attachBlock,
  appendNotebookBlock,
  getNotebook,
  getTrajectory,
  launchParkedQuestion,
  listInvestigations,
  listWatchForLater,
  postTypedEvent,
  reorderBlock,
  searchBlocks,
  undoAiAction,
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

    await expect(launchParkedQuestion("q-1")).resolves.toEqual({
      investigation_id: "inv-new",
      status: "in_progress",
      start_event_id: "evt-start",
    });

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

    await expect(getNotebook("nb-1")).resolves.toEqual({
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

    const result = await appendNotebookBlock("nb-append", {
      block_type: "note",
      content: { text: "x" },
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
  });
});
