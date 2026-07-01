import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parkQuestionForLater } from "./api";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset().mockResolvedValue(
    new Response(JSON.stringify({
      event_id: "evt-park",
      action_type: "question.identified",
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("crypto", {
    randomUUID: () => "extension-uuid",
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parkQuestionForLater", () => {
  it("emits a question.identified typed event that watch-for-later can read", async () => {
    const result = await parkQuestionForLater({
      investigation_id: "inv-source",
      question_text: "What evidence would show retrieval feels like memory?",
      source_document_id: "doc-source",
      anchor_region_id: "region-1",
      parent_event_id: "event-parent",
    });

    expect(result.question_id).toBe("q-extension-uuid");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body as string)).toEqual({
      investigation_id: "inv-source",
      document_id: "doc-source",
      parent_event_id: "event-parent",
      role: "operator",
      policy_id: "operator/brainstorm",
      payload: {
        action_type: "question.identified",
        question_id: "q-extension-uuid",
        question_text: "What evidence would show retrieval feels like memory?",
        anchor_region_id: "region-1",
      },
    });
  });
});
