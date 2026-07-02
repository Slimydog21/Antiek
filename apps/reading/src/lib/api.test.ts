import { beforeEach, describe, expect, it, vi } from "vitest";

import { startInvestigation } from "./api";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function postedJsonBody(): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(typeof init.body).toBe("string");
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("lib/api startInvestigation boundary", () => {
  it("trims launch request text and optional handles before sending", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        investigation_id: " inv-started ",
        status: "in_progress",
        start_event_id: " ev-start ",
      }),
    );

    await expect(
      startInvestigation({
        question: "  What changed?  ",
        context: "  source passage  ",
        topic_slug: "  climate-risk  ",
        parent_investigation_id: " inv-parent ",
        spawn_context: " selected passage ",
        max_sub_questions: 3,
        investigation_id: " inv-reserved ",
        research_tier: "fast",
      }),
    ).resolves.toEqual({
      investigation_id: "inv-started",
      status: "in_progress",
      start_event_id: "ev-start",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/investigations");
    expect(postedJsonBody()).toEqual({
      question: "What changed?",
      context: "source passage",
      topic_slug: "climate-risk",
      parent_investigation_id: "inv-parent",
      spawn_context: "selected passage",
      max_sub_questions: 3,
      investigation_id: "inv-reserved",
      research_tier: "fast",
    });
  });

  it("drops blank optional launch fields and unsupported research tiers", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        investigation_id: "inv-started",
        status: "in_progress",
        start_event_id: "ev-start",
      }),
    );

    await startInvestigation({
      question: "Question",
      context: " ",
      topic_slug: " ",
      parent_investigation_id: " ",
      spawn_context: " ",
      investigation_id: " ",
      research_tier: "turbo" as "deep",
    });

    expect(postedJsonBody()).toEqual({ question: "Question" });
  });

  it("rejects malformed launch requests before sending", async () => {
    await expect(startInvestigation({ question: " " })).rejects.toThrow(/question/);
    await expect(
      startInvestigation({ question: "Question", max_sub_questions: 0 }),
    ).rejects.toThrow(/max_sub_questions/);
    await expect(
      startInvestigation({ question: "Question", max_sub_questions: Number.POSITIVE_INFINITY }),
    ).rejects.toThrow(/max_sub_questions/);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
