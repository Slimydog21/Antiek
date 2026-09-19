import { afterEach, describe, expect, it, vi } from "vitest";

import {
  launchParkedQuestion,
  launchReservedQuestion,
  startInvestigation,
} from "./api";
import { spinResearch } from "../api/books";

describe("startInvestigation signed quote transport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("preflights the exact command and submits only the returned token addition", async () => {
    const request = {
      question: "What is true?",
      context: "Exact context",
      parent_investigation_id: "inv-parent",
      spawn_context: "selected passage",
      max_sub_questions: 7,
      research_tier: "wrestle" as const,
      approved_run_ceiling_usd: 2.25,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ quote_token: "rq1.payload.signature" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            investigation_id: "inv-child",
            status: "accepted",
            start_event_id: "evt-start",
          }),
          { status: 202 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(startInvestigation(request)).resolves.toMatchObject({
      investigation_id: "inv-child",
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [quoteUrl, quoteInit] = fetchMock.mock.calls[0];
    const [launchUrl, launchInit] = fetchMock.mock.calls[1];
    expect(quoteUrl).toBe("/investigations/quote");
    expect(JSON.parse(String(quoteInit.body))).toEqual(request);
    expect(launchUrl).toBe("/investigations");
    expect(JSON.parse(String(launchInit.body))).toEqual({
      ...request,
      research_quote_token: "rq1.payload.signature",
    });
    expect(quoteInit.credentials).toBe("include");
    expect(launchInit.credentials).toBe("include");
  });

  it("does not launch when quote issuance fails or is malformed", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "pricing unavailable" }), { status: 503 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      startInvestigation({ question: "What is true?", approved_run_ceiling_usd: 1 }),
    ).rejects.toThrow("POST /investigations/quote failed");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockReset().mockResolvedValue(new Response("{}", { status: 200 }));
    await expect(
      startInvestigation({ question: "What is true?", approved_run_ceiling_usd: 1 }),
    ).rejects.toThrow("invalid quote");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("preflights the exact reserved-question path and command", async () => {
    const request = {
      question: "Reserved question?",
      context: "parent context",
      research_tier: "deep" as const,
      approved_run_ceiling_usd: 1.5,
      approved_chase_ceiling_usd: 3,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ quote_token: "rq1.reserved.signature" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            investigation_id: "inv-reserved",
            status: "started",
            start_event_id: "evt-reserved",
          }),
          { status: 202 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    await launchReservedQuestion("parent/id", "question id", request);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/research/parent%2Fid/questions/question%20id/reserved-launch/quote",
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual(request);
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/research/parent%2Fid/questions/question%20id/reserved-launch",
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({
      ...request,
      research_quote_token: "rq1.reserved.signature",
    });
  });

  it("preflights a parked question before launch", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ quote_token: "rq1.parked.signature" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            investigation_id: "inv-parked",
            status: "started",
            start_event_id: "evt-parked",
          }),
          { status: 202 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    await launchParkedQuestion("question/id", 1.25);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/watch-for-later/question%2Fid/launch/quote",
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({
      approved_run_ceiling_usd: 1.25,
    });
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/watch-for-later/question%2Fid/launch",
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({
      approved_run_ceiling_usd: 1.25,
      research_quote_token: "rq1.parked.signature",
    });
  });

  it("preflights the exact book-passage path and body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ quote_token: "rq1.book.signature" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ investigation_id: "inv-book" }), {
          status: 202,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    await spinResearch("doc/id", 4, "selected text", {
      researchTier: "wrestle",
      approvedRunCeilingUsd: 2.5,
    });
    const expected = {
      page_index: 4,
      passage_text: "selected text",
      approved_run_ceiling_usd: 2.5,
      research_tier: "wrestle",
    };
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/books/doc%2Fid/spin-research/quote",
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual(expected);
    expect(fetchMock.mock.calls[1][0]).toBe("/books/doc%2Fid/spin-research");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({
      ...expected,
      research_quote_token: "rq1.book.signature",
    });
  });
});
