import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * books api — Read client boundaries.
 *
 * Surface tests pin component-level call shapes. This file pins API-client wire
 * contracts: talk-to-book defaults/errors, voice-note confirmation, ad
 * impressions, spin-research, meta-reading defaults/errors, and personal-space
 * filing suggestions.
 */

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", () => ({
  API_BASE: "/api",
  apiFetch: apiFetchMock,
}));

import {
  askBook,
  generateMetaReading,
  getFileSuggestion,
  recordAdImpressions,
  saveVoiceNote,
  spinResearch,
  transcribeAudio,
} from "./books";

function askBookResponse() {
  return {
    answer: "Page seven discusses entanglement.",
    citations: [
      {
        chunk_id: "chunk-7",
        document_id: "doc-1",
        page_index: 6,
        page_resolved: true,
        snippet: "the cited passage",
      },
    ],
    grounded: true,
    context_chunk_count: 1,
  };
}

function metaReadingResponse() {
  return {
    asset_id: "mr-api-1",
    report: "owned-corpus synthesis",
    citations: [],
    length_unit: "pages",
    length_amount: 3,
    word_budget: 900,
    truncated: false,
    corpus_scope: "hard",
    corpus_document_ids: ["doc-1"],
    empty: false,
    context_chunk_count: 1,
  };
}

function voiceNoteResponse() {
  return {
    voice_note_id: "vnote-1",
    document_id: "doc-voice",
    page_index: 2,
    note_count: 2,
    notes: ["insight a", "question b"],
    emitted_event_ids: ["ev-1", "ev-2"],
  };
}

function spinResearchResponse() {
  return {
    investigation_id: "inv-child",
    document_id: "doc-spin",
    page_index: 4,
    gated: false,
    servability: "public_domain",
    seed_preview: "seed preview",
  };
}

function postedJsonBody(): Record<string, unknown> {
  const [, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
  expect(typeof init.body).toBe("string");
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue(
    new Response(JSON.stringify(metaReadingResponse()), { status: 200 }),
  );
});

describe("books api — talk-to-book boundary", () => {
  it("asks one encoded book with empty history and the default deep tier", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(askBookResponse()), { status: 200 }),
    );

    const result = await askBook("doc with space", "what is on page seven?");

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/books/doc%20with%20space/ask");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(postedJsonBody()).toEqual({
      question: "what is on page seven?",
      history: [],
      research_tier: "deep",
    });
    expect(result).toEqual(askBookResponse());
  });

  it("preserves explicit history and fast tier for multi-turn continuation", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(askBookResponse()), { status: 200 }),
    );

    await askBook("doc-1", "what about that?", {
      history: [{ question: "first question", answer: "first answer" }],
      researchTier: "fast",
    });

    expect(postedJsonBody()).toEqual({
      question: "what about that?",
      history: [{ question: "first question", answer: "first answer" }],
      research_tier: "fast",
    });
  });

  it("surfaces an unknown book as the reader's book_not_found branch", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("missing", { status: 404 }));

    await expect(askBook("missing-doc", "anything")).rejects.toThrow("book_not_found");
  });

  it("surfaces provider unavailability as the reader-facing talk-to-book message", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no model", { status: 503 }));

    await expect(askBook("doc-1", "anything")).rejects.toThrow(
      /Talk-to-book isn.t available right now\./,
    );
  });

  it("keeps unexpected ask failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(askBook("doc-1", "anything")).rejects.toThrow(
      "POST /books/{id}/ask: HTTP 500",
    );
  });
});

describe("books api — voice-note boundary", () => {
  it("posts captured audio with its media type and parses the transcript", async () => {
    const transcript = {
      transcript: "the author argues X",
      language: "en",
      duration_seconds: 3,
    };
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(transcript), { status: 200 }),
    );
    const audio = new Blob(["audio"], { type: "audio/ogg" });

    const result = await transcribeAudio(audio);

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/voice/transcribe");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "audio/ogg" });
    expect(init.body).toBe(audio);
    expect(result).toEqual(transcript);
  });

  it("uses audio/webm when the captured audio has no media type", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ transcript: "", language: null, duration_seconds: 0 }), {
        status: 200,
      }),
    );
    const audio = new Blob(["audio"]);

    await transcribeAudio(audio);

    const [, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toMatchObject({ "Content-Type": "audio/webm" });
  });

  it("surfaces empty audio and missing transcription provider honestly", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("empty", { status: 400 }));
    await expect(transcribeAudio(new Blob([]))).rejects.toThrow("No audio captured.");

    apiFetchMock.mockResolvedValueOnce(new Response("no whisper", { status: 503 }));
    await expect(transcribeAudio(new Blob(["audio"]))).rejects.toThrow(
      /Transcription isn.t available right now\./,
    );
  });

  it("keeps unexpected transcription failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(transcribeAudio(new Blob(["audio"]))).rejects.toThrow(
      "POST /voice/transcribe: HTTP 500",
    );
  });

  it("saves a corrected transcript with confirmed true and optional audio provenance", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(voiceNoteResponse()), { status: 200 }),
    );

    const result = await saveVoiceNote("doc voice", {
      page_index: 2,
      transcript: "the author argues X",
      investigation_id: "read-doc-voice",
      audio_ref: "blob://clip-1",
      capture_event_id: "ev-capture",
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/books/doc%20voice/voice-note");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(postedJsonBody()).toEqual({
      page_index: 2,
      transcript: "the author argues X",
      investigation_id: "read-doc-voice",
      audio_ref: "blob://clip-1",
      capture_event_id: "ev-capture",
      confirmed: true,
    });
    expect(result).toEqual(voiceNoteResponse());
  });

  it("surfaces unconfirmed-transcript and unavailable-distiller save failures", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("unconfirmed", { status: 400 }));
    await expect(
      saveVoiceNote("doc-1", {
        page_index: 0,
        transcript: "draft",
        investigation_id: "read-doc-1",
      }),
    ).rejects.toThrow("Confirm the transcript before saving.");

    apiFetchMock.mockResolvedValueOnce(new Response("no distiller", { status: 503 }));
    await expect(
      saveVoiceNote("doc-1", {
        page_index: 0,
        transcript: "confirmed draft",
        investigation_id: "read-doc-1",
      }),
    ).rejects.toThrow(/note distiller isn.t available right now\./);
  });

  it("keeps unexpected voice-note save failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(
      saveVoiceNote("doc-1", {
        page_index: 0,
        transcript: "confirmed draft",
        investigation_id: "read-doc-1",
      }),
    ).rejects.toThrow("POST /books/{id}/voice-note: HTTP 500");
  });
});

describe("books api — ad impression boundary", () => {
  it("does nothing when there are no impressions to flush", async () => {
    await recordAdImpressions("doc-1", "session-1", []);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("posts reader impressions with session id and keepalive", async () => {
    await recordAdImpressions("doc with space", "session-1", [
      {
        slot_id: "slot:doc:p0:top",
        page_index: 0,
        fill_kind: "house",
        revenue_usd_cents: 0,
        focused_dwell_ms: 1200,
        tab_focused: true,
      },
      {
        slot_id: "slot:doc:p0:bottom",
        page_index: 0,
        fill_kind: "ad",
        revenue_usd_cents: 42,
        focused_dwell_ms: 900,
        tab_focused: true,
      },
    ]);

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/books/doc%20with%20space/ad-impressions");
    expect(init.method).toBe("POST");
    expect(init.keepalive).toBe(true);
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(postedJsonBody()).toEqual({
      session_id: "session-1",
      impressions: [
        {
          slot_id: "slot:doc:p0:top",
          page_index: 0,
          fill_kind: "house",
          revenue_usd_cents: 0,
          focused_dwell_ms: 1200,
          tab_focused: true,
        },
        {
          slot_id: "slot:doc:p0:bottom",
          page_index: 0,
          fill_kind: "ad",
          revenue_usd_cents: 42,
          focused_dwell_ms: 900,
          tab_focused: true,
        },
      ],
    });
  });

  it("does not disrupt reading when the impression flush is rejected", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("offline"));

    await expect(
      recordAdImpressions("doc-1", "session-1", [
        {
          slot_id: "slot:doc:p0:top",
          page_index: 0,
          fill_kind: "house",
          revenue_usd_cents: 0,
          focused_dwell_ms: 1200,
          tab_focused: true,
        },
      ]),
    ).resolves.toBeUndefined();
  });

  it("does not disrupt reading when the impression endpoint returns an error", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(
      recordAdImpressions("doc-1", "session-1", [
        {
          slot_id: "slot:doc:p0:top",
          page_index: 0,
          fill_kind: "ad",
          revenue_usd_cents: 42,
          focused_dwell_ms: 900,
          tab_focused: true,
        },
      ]),
    ).resolves.toBeUndefined();
  });
});

describe("books api — spin-research boundary", () => {
  it("posts a gate-safe page spin request with passage text and parses the child research", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(spinResearchResponse()), { status: 200 }),
    );

    const result = await spinResearch("doc spin", 4, "selected passage");

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/books/doc%20spin/spin-research");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(postedJsonBody()).toEqual({
      page_index: 4,
      passage_text: "selected passage",
    });
    expect(result).toEqual(spinResearchResponse());
  });

  it("trims non-empty selected passage text", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(spinResearchResponse()), { status: 200 }),
    );

    await spinResearch("doc-1", 0, "  selected passage  ");

    expect(postedJsonBody()).toEqual({
      page_index: 0,
      passage_text: "selected passage",
    });
  });

  it("sends null passage text when the reader has no selected passage", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(spinResearchResponse()), { status: 200 }),
    );

    await spinResearch("doc-1", 0);

    expect(postedJsonBody()).toEqual({
      page_index: 0,
      passage_text: null,
    });
  });

  it("sends null passage text when the selected passage is empty", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(spinResearchResponse()), { status: 200 }),
    );

    await spinResearch("doc-1", 0, "   ");

    expect(postedJsonBody()).toEqual({
      page_index: 0,
      passage_text: null,
    });
  });

  it("parses future servability values without narrowing them away", async () => {
    const futureResponse = { ...spinResearchResponse(), servability: "future_open" };
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(futureResponse), { status: 200 }),
    );

    await expect(spinResearch("doc-1", 0)).resolves.toEqual(futureResponse);
  });

  it("surfaces an unknown book as the reader's book_not_found branch", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("missing", { status: 404 }));

    await expect(spinResearch("missing-doc", 0)).rejects.toThrow("book_not_found");
  });

  it("surfaces provider unavailability as the reader-facing spin-research message", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no model", { status: 503 }));

    await expect(spinResearch("doc-1", 0)).rejects.toThrow(
      /Spin research isn.t available right now\./,
    );
  });

  it("keeps unexpected spin failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(spinResearch("doc-1", 0)).rejects.toThrow(
      "POST /books/{id}/spin-research: HTTP 500",
    );
  });
});

describe("books api — meta-reading boundary", () => {
  it("defaults meta-reading generation to the proposed hard owned-corpus scope", async () => {
    const result = await generateMetaReading({
      prompt: "free will across my books",
      length_unit: "pages",
      length_amount: 3,
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/corpus/meta-reading");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(postedJsonBody()).toEqual({
      prompt: "free will across my books",
      length_unit: "pages",
      length_amount: 3,
      research_tier: "deep",
      corpus_scope: "hard",
    });
    expect(result).toEqual(metaReadingResponse());
  });

  it("preserves explicit rollback scope, tier, and document picks", async () => {
    await generateMetaReading({
      prompt: "owned corpus with explicit picks",
      length_unit: "minutes",
      length_amount: 12,
      research_tier: "fast",
      corpus_scope: "soft",
      document_ids: ["doc-a", "doc-b"],
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(postedJsonBody()).toEqual({
      prompt: "owned corpus with explicit picks",
      length_unit: "minutes",
      length_amount: 12,
      research_tier: "fast",
      corpus_scope: "soft",
      document_ids: ["doc-a", "doc-b"],
    });
  });

  it("surfaces the backend's stated length-bound error", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Length is capped at 60 pages; got 999." }),
        { status: 422 },
      ),
    );

    await expect(
      generateMetaReading({
        prompt: "too long",
        length_unit: "pages",
        length_amount: 999,
      }),
    ).rejects.toThrow("Length is capped at 60 pages; got 999.");
  });

  it("falls back when a length-bound error omits a string detail", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: [{ msg: "bad length" }] }), {
        status: 422,
      }),
    );

    await expect(
      generateMetaReading({
        prompt: "too long",
        length_unit: "pages",
        length_amount: 999,
      }),
    ).rejects.toThrow("Invalid length.");
  });

  it("surfaces provider unavailability as the reader-facing meta-reading message", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no model", { status: 503 }));

    await expect(
      generateMetaReading({
        prompt: "summarize",
        length_unit: "minutes",
        length_amount: 10,
      }),
    ).rejects.toThrow(/Meta-reading isn.t available right now\./);
  });

  it("keeps unexpected backend failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(
      generateMetaReading({
        prompt: "summarize",
        length_unit: "pages",
        length_amount: 3,
      }),
    ).rejects.toThrow("POST /corpus/meta-reading: HTTP 500");
  });
});

describe("books api — file suggestion boundary", () => {
  const suggestionResponse = {
    document_id: "doc with space",
    matches: [
      {
        investigation_id: "inv-1",
        question: "free will and determinism",
        score: 0.72,
      },
    ],
  };

  it("requests a suggestion for one encoded document id and parses matches", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(suggestionResponse), { status: 200 }),
    );

    const result = await getFileSuggestion("doc with space");

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(apiFetchMock.mock.calls[0][0]).toBe(
      "/api/meta-readings/file-suggestion?document_id=doc+with+space",
    );
    expect(result).toEqual(suggestionResponse);
  });

  it("escapes query-control characters in the document id", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ...suggestionResponse, document_id: "doc&id=1" }), {
        status: 200,
      }),
    );

    await getFileSuggestion("doc&id=1");

    expect(apiFetchMock.mock.calls[0][0]).toBe(
      "/api/meta-readings/file-suggestion?document_id=doc%26id%3D1",
    );
  });

  it("treats embedder unavailability as no suggestion, not a filing failure", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no embedder", { status: 503 }));

    await expect(getFileSuggestion("doc-1")).resolves.toEqual({
      document_id: "doc-1",
      matches: [],
    });
  });

  it("keeps unexpected suggestion failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(getFileSuggestion("doc-1")).rejects.toThrow(
      "GET /meta-readings/file-suggestion: HTTP 500",
    );
  });
});
