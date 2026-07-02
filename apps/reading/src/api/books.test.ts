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
  curateBooks,
  generateMetaReading,
  getBook,
  getBookFullText,
  getFileSuggestion,
  getSavedMetaReading,
  listBooks,
  listPersonalSpace,
  listPersonalSpaceCategories,
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

describe("books api — source-book boundary", () => {
  it("lists encoded corpus status and sanitizes source-book summaries", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          books: [
            {
              document_id: "  doc-1  ",
              title: "  The Book  ",
              author: "  Author  ",
              servability: "future_open",
              servable_full_text: true,
              page_count: "12",
              cover_uri: "  https://example.test/cover.png  ",
              ip_holder_id: 123,
              taken_down: false,
            },
            {
              document_id: " ",
              title: "No identity",
              servability: "public_domain",
              servable_full_text: true,
            },
          ],
          count: "2",
        }),
        { status: 200 },
      ),
    );

    const result = await listBooks("gated");

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/books?status=gated");
    expect(result).toEqual({
      books: [
        {
          document_id: "doc-1",
          title: "The Book",
          author: "Author",
          servability: "gated_metadata_only",
          servable_full_text: false,
          page_count: 0,
          cover_uri: "https://example.test/cover.png",
          ip_holder_id: null,
          taken_down: false,
        },
      ],
      count: 1,
    });
  });

  it("dedupes duplicate source-book ids after trimming", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          books: [
            {
              document_id: " doc-dup ",
              title: "First title",
              author: "Ada",
              servability: "public_domain",
              servable_full_text: true,
            },
            {
              document_id: "doc-dup",
              title: "Duplicate title",
              author: "Grace",
              servability: "publisher_opted_in",
              servable_full_text: true,
            },
            {
              document_id: "doc-other",
              title: "Other title",
              author: "Lin",
              servability: "platform_authored",
              servable_full_text: true,
            },
          ],
          count: "3",
        }),
        { status: 200 },
      ),
    );

    await expect(listBooks("all")).resolves.toMatchObject({
      books: [
        {
          document_id: "doc-dup",
          title: "First title",
          author: "Ada",
        },
        {
          document_id: "doc-other",
          title: "Other title",
          author: "Lin",
        },
      ],
      count: 2,
    });
  });

  it("sanitizes one book detail and its table of contents", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          document_id: "  doc-1  ",
          title: "  The Book  ",
          author: null,
          servability: "taken_down",
          servable_full_text: true,
          page_count: 9,
          cover_uri: "",
          ip_holder_id: "  rights-1  ",
          taken_down: false,
          pagination_scheme: "  page_markers  ",
          provenance: "  archive  ",
          license_basis: " ",
          toc: [
            { title: "  Chapter 1  ", page_index: 0, level: 0 },
            { title: "Bad page", page_index: "2", level: "1" },
            { title: " ", page_index: 1, level: 1 },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(getBook("doc 1")).resolves.toEqual({
      document_id: "doc-1",
      title: "The Book",
      author: null,
      servability: "taken_down",
      servable_full_text: false,
      page_count: 9,
      cover_uri: null,
      ip_holder_id: "rights-1",
      taken_down: true,
      pagination_scheme: "page_markers",
      provenance: "archive",
      license_basis: null,
      toc: [
        { title: "Chapter 1", page_index: 0, level: 0 },
        { title: "Bad page", page_index: null, level: 1 },
      ],
    });
    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/books/doc%201");
  });

  it("trims source-book request ids before encoding them", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          document_id: "doc-1",
          title: "The Book",
          servability: "public_domain",
          servable_full_text: true,
        }),
        { status: 200 },
      ),
    );

    await getBook(" doc 1 ");

    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/books/doc%201");
  });

  it("rejects malformed book detail identity", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ document_id: " ", title: "Missing id" }), {
        status: 200,
      }),
    );

    await expect(getBook("doc-1")).rejects.toThrow("Malformed book response.");
  });

  it("sanitizes full-text responses without widening the legal gate", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          document_id: "  doc-1  ",
          servable: true,
          servability: "public_domain",
          full_text: 7,
          snippet: "preview",
          structured_blocks: "{\"blocks\":[]}",
          representative_chunk_id: " chunk-1 ",
          title: "  The Book  ",
          author: "  Author  ",
          reason: " ",
          tier: "T4",
          ad_eligible: true,
          canonical_url: "  https://arxiv.org/abs/1  ",
          license: " ",
        }),
        { status: 200 },
      ),
    );

    await expect(getBookFullText("doc 1")).resolves.toEqual({
      document_id: "doc-1",
      servable: false,
      servability: "public_domain",
      full_text: null,
      snippet: "preview",
      structured_blocks: null,
      representative_chunk_id: null,
      title: "The Book",
      author: "Author",
      reason: "not_servable",
      tier: null,
      ad_eligible: false,
      canonical_url: "https://arxiv.org/abs/1",
      license: null,
    });
    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/books/doc%201/full-text");
  });

  it.each([
    "javascript:alert(1)",
    "data:text/html,owned",
    "/abs/2401.00001",
    "http://arxiv.org/abs/2401.00001",
    "https://evil.example/abs/2401.00001",
    "https://arxiv.org/pdf/2401.00001",
  ])("nulls unsafe or non-canonical arXiv full-text links: %s", async (canonical_url) => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          document_id: "doc-arxiv",
          servable: false,
          full_text: null,
          snippet: null,
          reason: "rights_tier_linkback",
          tier: "T2",
          ad_eligible: false,
          canonical_url,
        }),
        { status: 200 },
      ),
    );

    await expect(getBookFullText("doc-arxiv")).resolves.toMatchObject({
      document_id: "doc-arxiv",
      tier: "T2",
      canonical_url: null,
    });
  });

  it("rejects blank source-book request ids before sending", async () => {
    await expect(getBook(" ")).rejects.toThrow(/documentId/);
    await expect(getBookFullText(" ")).rejects.toThrow(/documentId/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("rejects malformed full-text identity", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ document_id: "", servable: false }), { status: 200 }),
    );

    await expect(getBookFullText("doc-1")).rejects.toThrow(
      "Malformed book full-text response.",
    );
  });
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

  it("trims talk-to-book request ids and questions before sending", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(askBookResponse()), { status: 200 }),
    );

    await askBook(" doc with space ", "  what is on page seven?  ");

    const [url] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/books/doc%20with%20space/ask");
    expect(postedJsonBody()).toMatchObject({
      question: "what is on page seven?",
    });
  });

  it("rejects malformed talk-to-book request inputs before sending", async () => {
    await expect(askBook(" ", "question")).rejects.toThrow(/documentId/);
    await expect(askBook("doc-1", " ")).rejects.toThrow(/question/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("preserves explicit history and fast tier for multi-turn continuation", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(askBookResponse()), { status: 200 }),
    );

    await askBook("doc-1", "what about that?", {
      history: [{ question: " first question ", answer: " first answer " }],
      researchTier: "fast",
    });

    expect(postedJsonBody()).toEqual({
      question: "what about that?",
      history: [{ question: "first question", answer: "first answer" }],
      research_tier: "fast",
    });
  });

  it("drops malformed talk-to-book history and defaults unknown tiers to deep", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(askBookResponse()), { status: 200 }),
    );

    await askBook("doc-1", "what about that?", {
      history: [
        { question: " ", answer: "missing question" },
        { question: "missing answer", answer: " " },
        { question: "usable question", answer: "usable answer" },
      ],
      researchTier: "medium" as never,
    });

    expect(postedJsonBody()).toEqual({
      question: "what about that?",
      history: [{ question: "usable question", answer: "usable answer" }],
      research_tier: "deep",
    });
  });

  it("sanitizes talk-to-book citations before they reach bookmark state", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          answer: "  Cited answer.  ",
          citations: [
            {
              chunk_id: " chunk-7 ",
              document_id: " doc-1 ",
              page_index: "6",
              page_resolved: true,
              snippet: "  page seven passage  ",
            },
            {
              chunk_id: "chunk-unresolved",
              document_id: "doc-1",
              page_index: 2,
              page_resolved: false,
              snippet: "unresolved passage",
            },
            {
              chunk_id: " ",
              document_id: "doc-1",
              page_index: 1,
              page_resolved: true,
              snippet: "missing chunk id",
            },
          ],
          grounded: true,
          context_chunk_count: "not a number",
        }),
        { status: 200 },
      ),
    );

    const result = await askBook("doc-1", "question");

    expect(result).toEqual({
      answer: "Cited answer.",
      citations: [
        {
          chunk_id: "chunk-7",
          document_id: "doc-1",
          page_index: null,
          page_resolved: false,
          snippet: "page seven passage",
        },
        {
          chunk_id: "chunk-unresolved",
          document_id: "doc-1",
          page_index: null,
          page_resolved: false,
          snippet: "unresolved passage",
        },
      ],
      grounded: true,
      context_chunk_count: 0,
    });
  });

  it("rejects malformed talk-to-book answers instead of persisting fake turns", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ answer: " ", citations: [] }), { status: 200 }),
    );

    await expect(askBook("doc-1", "anything")).rejects.toThrow(
      "Malformed talk-to-book response.",
    );
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

  it("sanitizes transcription responses before showing the draft transcript", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          transcript: "  the author argues X  ",
          language: "  en  ",
          duration_seconds: "3",
        }),
        { status: 200 },
      ),
    );

    await expect(transcribeAudio(new Blob(["audio"]))).resolves.toEqual({
      transcript: "the author argues X",
      language: "en",
      duration_seconds: 0,
    });
  });

  it("rejects malformed transcription responses", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ transcript: null }), { status: 200 }),
    );

    await expect(transcribeAudio(new Blob(["audio"]))).rejects.toThrow(
      "Malformed transcription response.",
    );
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

    const result = await saveVoiceNote(" doc voice ", {
      page_index: 2,
      transcript: " the author argues X ",
      investigation_id: " read-doc-voice ",
      audio_ref: " blob://clip-1 ",
      capture_event_id: " ev-capture ",
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

  it("nulls blank optional voice-note provenance before saving", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(voiceNoteResponse()), { status: 200 }),
    );

    await saveVoiceNote("doc-voice", {
      page_index: 2,
      transcript: "confirmed transcript",
      investigation_id: "read-doc-voice",
      audio_ref: " ",
      capture_event_id: " ",
    });

    expect(postedJsonBody()).toEqual({
      page_index: 2,
      transcript: "confirmed transcript",
      investigation_id: "read-doc-voice",
      audio_ref: null,
      capture_event_id: null,
      confirmed: true,
    });
  });

  it("sanitizes saved voice-note responses before adding notes to reader state", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          voice_note_id: "  vnote-1  ",
          document_id: "  doc-voice  ",
          page_index: 2,
          note_count: "2",
          notes: [" insight a ", "", 9, " question b "],
          emitted_event_ids: [" ev-1 ", null, "ev-2"],
        }),
        { status: 200 },
      ),
    );

    await expect(
      saveVoiceNote("doc-voice", {
        page_index: 2,
        transcript: "confirmed",
        investigation_id: "read-doc-voice",
      }),
    ).resolves.toEqual({
      voice_note_id: "vnote-1",
      document_id: "doc-voice",
      page_index: 2,
      note_count: 2,
      notes: ["insight a", "question b"],
      emitted_event_ids: ["ev-1", "ev-2"],
    });
  });

  it("rejects malformed voice-note save responses", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ voice_note_id: "vnote", document_id: "doc" }), {
        status: 200,
      }),
    );

    await expect(
      saveVoiceNote("doc-voice", {
        page_index: 2,
        transcript: "confirmed",
        investigation_id: "read-doc-voice",
      }),
    ).rejects.toThrow("Malformed voice-note response.");
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

  it.each([1.5, -1, Number.MAX_SAFE_INTEGER + 1, Number.POSITIVE_INFINITY])(
    "rejects malformed voice-note page index %s before sending",
    async (page_index) => {
      await expect(
        saveVoiceNote("doc-1", {
          page_index,
          transcript: "confirmed draft",
          investigation_id: "read-doc-1",
        }),
      ).rejects.toThrow(/page_index/);
      expect(apiFetchMock).not.toHaveBeenCalled();
    },
  );

  it("rejects malformed voice-note request handles before sending", async () => {
    await expect(
      saveVoiceNote(" ", {
        page_index: 0,
        transcript: "confirmed draft",
        investigation_id: "read-doc-1",
      }),
    ).rejects.toThrow(/documentId/);
    await expect(
      saveVoiceNote("doc-1", {
        page_index: 0,
        transcript: " ",
        investigation_id: "read-doc-1",
      }),
    ).rejects.toThrow(/transcript/);
    await expect(
      saveVoiceNote("doc-1", {
        page_index: 0,
        transcript: "confirmed draft",
        investigation_id: " ",
      }),
    ).rejects.toThrow(/investigation_id/);

    expect(apiFetchMock).not.toHaveBeenCalled();
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

  it("posts reader impressions with trimmed handles, session id, and keepalive", async () => {
    await recordAdImpressions(" doc with space ", " session-1 ", [
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

  it("does not flush reader impressions with malformed flush handles", async () => {
    await recordAdImpressions(" ", "session-1", [
      {
        slot_id: "slot:doc:p0:top",
        page_index: 0,
        fill_kind: "house",
        revenue_usd_cents: 0,
        focused_dwell_ms: 1200,
        tab_focused: true,
      },
    ]);
    await recordAdImpressions("doc-1", " ", [
      {
        slot_id: "slot:doc:p0:top",
        page_index: 0,
        fill_kind: "house",
        revenue_usd_cents: 0,
        focused_dwell_ms: 1200,
        tab_focused: true,
      },
    ]);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("drops malformed impressions before flushing valid ones", async () => {
    await recordAdImpressions("doc-1", "session-1", [
      {
        slot_id: "  slot:doc:p0:top  ",
        page_index: 0,
        fill_kind: "house",
        revenue_usd_cents: 0,
        focused_dwell_ms: 1200.5,
        tab_focused: true,
      },
      {
        slot_id: "slot:bad:fractional-page",
        page_index: 0.5,
        fill_kind: "ad",
        revenue_usd_cents: 10,
        focused_dwell_ms: 500,
        tab_focused: true,
      },
      {
        slot_id: "slot:bad:negative-revenue",
        page_index: 0,
        fill_kind: "ad",
        revenue_usd_cents: -1,
        focused_dwell_ms: 500,
        tab_focused: true,
      },
      {
        slot_id: "slot:bad:infinite-dwell",
        page_index: 0,
        fill_kind: "ad",
        revenue_usd_cents: 10,
        focused_dwell_ms: Number.POSITIVE_INFINITY,
        tab_focused: true,
      },
    ]);

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(postedJsonBody()).toEqual({
      session_id: "session-1",
      impressions: [
        {
          slot_id: "slot:doc:p0:top",
          page_index: 0,
          fill_kind: "house",
          revenue_usd_cents: 0,
          focused_dwell_ms: 1200.5,
          tab_focused: true,
        },
      ],
    });
  });

  it("does not flush when every impression is malformed", async () => {
    await recordAdImpressions("doc-1", "session-1", [
      {
        slot_id: "",
        page_index: 0,
        fill_kind: "house",
        revenue_usd_cents: 0,
        focused_dwell_ms: 100,
        tab_focused: true,
      },
      {
        slot_id: "slot:bad:unsafe-page",
        page_index: Number.MAX_SAFE_INTEGER + 1,
        fill_kind: "ad",
        revenue_usd_cents: 10,
        focused_dwell_ms: 100,
        tab_focused: true,
      },
    ]);

    expect(apiFetchMock).not.toHaveBeenCalled();
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

  it("trims spin-research request ids before encoding them", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(spinResearchResponse()), { status: 200 }),
    );

    await spinResearch(" doc spin ", 0);

    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/books/doc%20spin/spin-research");
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

  it.each([1.5, -1, Number.MAX_SAFE_INTEGER + 1, Number.POSITIVE_INFINITY])(
    "rejects malformed page index %s before sending a spin request",
    async (pageIndex) => {
      await expect(spinResearch("doc-1", pageIndex)).rejects.toThrow(/page_index/);
      expect(apiFetchMock).not.toHaveBeenCalled();
    },
  );

  it("rejects malformed spin-research document ids before sending", async () => {
    await expect(spinResearch(" ", 0)).rejects.toThrow(/documentId/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("parses future servability values without narrowing them away", async () => {
    const futureResponse = { ...spinResearchResponse(), servability: "future_open" };
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(futureResponse), { status: 200 }),
    );

    await expect(spinResearch("doc-1", 0)).resolves.toEqual(futureResponse);
  });

  it("sanitizes spin-research launch responses before navigation", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          investigation_id: "  inv-child  ",
          document_id: "  doc-spin  ",
          page_index: 4,
          gated: "yes",
          servability: "  future_open  ",
          seed_preview: "  selected seed  ",
        }),
        { status: 200 },
      ),
    );

    await expect(spinResearch("doc-1", 4)).resolves.toEqual({
      investigation_id: "inv-child",
      document_id: "doc-spin",
      page_index: 4,
      gated: false,
      servability: "future_open",
      seed_preview: "selected seed",
    });
  });

  it("rejects malformed spin-research launch responses", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ investigation_id: " ", document_id: "doc" }), {
        status: 200,
      }),
    );

    await expect(spinResearch("doc-1", 0)).rejects.toThrow(
      "Malformed spin-research response.",
    );
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

describe("books api — curate boundary", () => {
  it("requests curation with encoded prompt and limit", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          prompt: "stoicism",
          books: [
            { document_id: "doc-1", title: "Meditations", author: "Marcus", score: 0.9 },
          ],
        }),
        { status: 200 },
      ),
    );

    const result = await curateBooks(" stoicism & fate ", 7);

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(apiFetchMock.mock.calls[0][0]).toBe(
      "/api/books/curate?prompt=stoicism+%26+fate&limit=7",
    );
    expect(result).toEqual({
      prompt: "stoicism",
      books: [
        { document_id: "doc-1", title: "Meditations", author: "Marcus", score: 0.9 },
      ],
    });
  });

  it("sanitizes curated books before ranking the shelf", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          prompt: " ",
          books: [
            {
              document_id: "  doc-1  ",
              title: "  Meditations  ",
              author: "  Marcus  ",
              score: "0.9",
            },
            {
              document_id: " ",
              title: "Missing identity",
              author: "A",
              score: 1,
            },
            {
              document_id: "doc-2",
              title: null,
              author: "",
              score: 0.4,
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(curateBooks("stoicism")).resolves.toEqual({
      prompt: "stoicism",
      books: [
        { document_id: "doc-1", title: "Meditations", author: "Marcus", score: 0 },
        { document_id: "doc-2", title: null, author: null, score: 0.4 },
      ],
    });
  });

  it("dedupes duplicate curated book ids after trimming", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          prompt: "stoicism",
          books: [
            {
              document_id: " doc-dup ",
              title: "First curated",
              author: "Ada",
              score: 0.9,
            },
            {
              document_id: "doc-dup",
              title: "Duplicate curated",
              author: "Grace",
              score: 1,
            },
            {
              document_id: "doc-other",
              title: "Other curated",
              author: "Lin",
              score: 0.5,
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(curateBooks("stoicism")).resolves.toEqual({
      prompt: "stoicism",
      books: [
        { document_id: "doc-dup", title: "First curated", author: "Ada", score: 0.9 },
        { document_id: "doc-other", title: "Other curated", author: "Lin", score: 0.5 },
      ],
    });
  });

  it("rejects malformed curation requests before sending", async () => {
    await expect(curateBooks(" ")).rejects.toThrow(/prompt/);
    await expect(curateBooks("stoicism", 0)).rejects.toThrow(/limit/);
    await expect(curateBooks("stoicism", Number.POSITIVE_INFINITY)).rejects.toThrow(/limit/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("surfaces curation unavailability and unexpected failures", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no embedder", { status: 503 }));
    await expect(curateBooks("stoicism")).rejects.toThrow(
      "Curation is temporarily unavailable.",
    );

    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    await expect(curateBooks("stoicism")).rejects.toThrow(
      "GET /books/curate: HTTP 500",
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

  it("sanitizes generated meta-reading artifacts before they enter reader state", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          asset_id: "  mr-1  ",
          report: "  report  ",
          citations: [
            {
              chunk_id: " chunk-1 ",
              document_id: " doc-1 ",
              page_index: "2",
              page_resolved: true,
              snippet: "  cited text  ",
            },
          ],
          length_unit: "hours",
          length_amount: "3",
          word_budget: 900,
          truncated: "yes",
          corpus_scope: "wide",
          corpus_document_ids: [" doc-1 ", "", 7, "doc-1"],
          empty: "no",
          context_chunk_count: "bad",
        }),
        { status: 200 },
      ),
    );

    const result = await generateMetaReading({
      prompt: "dirty response",
      length_unit: "pages",
      length_amount: 3,
    });

    expect(result).toEqual({
      asset_id: "mr-1",
      report: "report",
      citations: [
        {
          chunk_id: "chunk-1",
          document_id: "doc-1",
          page_index: null,
          page_resolved: false,
          snippet: "cited text",
        },
      ],
      length_unit: "pages",
      length_amount: 0,
      word_budget: 900,
      truncated: false,
      corpus_scope: "hard",
      corpus_document_ids: ["doc-1"],
      empty: false,
      context_chunk_count: 0,
    });
  });

  it("rejects malformed generated meta-reading artifacts", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ asset_id: " ", report: "x" }), { status: 200 }),
    );

    await expect(
      generateMetaReading({
        prompt: "malformed",
        length_unit: "pages",
        length_amount: 3,
      }),
    ).rejects.toThrow("Malformed meta-reading response.");
  });

  it("preserves explicit rollback scope, tier, and document picks", async () => {
    await generateMetaReading({
      prompt: " owned corpus with explicit picks ",
      length_unit: "minutes",
      length_amount: 12,
      research_tier: "fast",
      corpus_scope: "soft",
      document_ids: [" doc-a ", " ", "doc-b", " doc-a ", "doc-b"],
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

  it("rejects malformed meta-reading requests before sending", async () => {
    await expect(
      generateMetaReading({
        prompt: " ",
        length_unit: "pages",
        length_amount: 3,
      }),
    ).rejects.toThrow(/prompt/);
    await expect(
      generateMetaReading({
        prompt: "valid",
        length_unit: "pages",
        length_amount: 0,
      }),
    ).rejects.toThrow(/length_amount/);
    await expect(
      generateMetaReading({
        prompt: "valid",
        length_unit: "pages",
        length_amount: Number.POSITIVE_INFINITY,
      }),
    ).rejects.toThrow(/length_amount/);

    expect(apiFetchMock).not.toHaveBeenCalled();
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

  it("falls back when a length-bound error body is not an object", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response("null", { status: 422 }),
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

describe("books api — saved meta-reading boundary", () => {
  it("requests one encoded saved meta-reading and sanitizes its artifact payload", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          asset_id: "  mr-saved  ",
          prompt: "  prompt  ",
          report: "  saved report  ",
          citations: [
            {
              chunk_id: " chunk-1 ",
              document_id: " doc-1 ",
              page_index: 4,
              page_resolved: true,
              snippet: "  cited text  ",
            },
          ],
          length_unit: "hours",
          length_amount: "5",
          truncated: "true",
          corpus_scope: "wide",
          corpus_document_ids: [" doc-1 ", null, "doc-2", " doc-1 "],
        }),
        { status: 200 },
      ),
    );

    const result = await getSavedMetaReading(" mr saved ");

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(apiFetchMock.mock.calls[0][0]).toBe("/api/meta-readings/mr%20saved");
    expect(result).toEqual({
      asset_id: "mr-saved",
      prompt: "prompt",
      report: "saved report",
      citations: [
        {
          chunk_id: "chunk-1",
          document_id: "doc-1",
          page_index: 4,
          page_resolved: true,
          snippet: "cited text",
        },
      ],
      length_unit: "pages",
      length_amount: 0,
      truncated: false,
      corpus_scope: "hard",
      corpus_document_ids: ["doc-1", "doc-2"],
    });
  });

  it("rejects malformed saved meta-reading artifacts", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ asset_id: "mr", prompt: " ", report: "x" }), {
        status: 200,
      }),
    );

    await expect(getSavedMetaReading("mr")).rejects.toThrow(
      "Malformed saved meta-reading response.",
    );
  });

  it("rejects blank saved meta-reading ids before sending", async () => {
    await expect(getSavedMetaReading(" ")).rejects.toThrow(/assetId/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });
});

describe("books api — personal-space boundary", () => {
  it("sanitizes the personal-space asset list", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          assets: [
            {
              asset_id: "  mr-1  ",
              kind: "future_kind",
              title: "  Meta read  ",
              prompt: "  prompt  ",
              document_ids: [" doc-1 ", "", 7, "doc-1"],
              emitted_at: "  2026-07-02T00:00:00Z  ",
              open_route: "  /read/meta/mr-1  ",
            },
            {
              asset_id: "bad",
              kind: "saved_read",
              title: "Bad",
              open_route: " ",
            },
            {
              asset_id: "  read:doc-2  ",
              kind: "saved_read",
              title: "  Saved book  ",
              document_ids: [" doc-2 "],
              emitted_at: null,
              open_route: "  /wrestle/doc-2  ",
            },
            {
              asset_id: "bad-route",
              kind: "meta_reading",
              title: "Bad route",
              document_ids: [],
              open_route: "/wrestle/mr-bad",
            },
          ],
          count: "4",
        }),
        { status: 200 },
      ),
    );

    await expect(listPersonalSpace()).resolves.toEqual({
      assets: [
        {
          asset_id: "mr-1",
          kind: "meta_reading",
          title: "Meta read",
          prompt: "prompt",
          document_ids: ["doc-1"],
          emitted_at: "2026-07-02T00:00:00Z",
          open_route: "/read/meta-reading/mr-1",
        },
        {
          asset_id: "read:doc-2",
          kind: "saved_read",
          title: "Saved book",
          prompt: null,
          document_ids: ["doc-2"],
          emitted_at: null,
          open_route: "/read/doc-2",
        },
      ],
      count: 2,
    });
  });

  it("dedupes duplicate personal-space asset ids after trimming", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          assets: [
            {
              asset_id: " asset-dup ",
              kind: "meta_reading",
              title: "First asset",
              document_ids: ["doc-1"],
              open_route: "/read/meta-reading/asset-dup",
            },
            {
              asset_id: "asset-dup",
              kind: "meta_reading",
              title: "Duplicate asset",
              document_ids: ["doc-2"],
              open_route: "/read/meta-reading/asset-dup-duplicate",
            },
            {
              asset_id: "asset-other",
              kind: "saved_read",
              title: "Other asset",
              document_ids: ["doc-other"],
              open_route: "/read/doc-other",
            },
          ],
          count: 3,
        }),
        { status: 200 },
      ),
    );

    await expect(listPersonalSpace()).resolves.toMatchObject({
      assets: [
        { asset_id: "asset-dup", title: "First asset", document_ids: ["doc-1"] },
        { asset_id: "asset-other", title: "Other asset", document_ids: ["doc-other"] },
      ],
      count: 2,
    });
  });

  it("sanitizes personal-space categories and falls back to recency ordering", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          categories: [
            {
              category_id: "  cat-1  ",
              label: "  Philosophy  ",
              asset_ids: [" mr-1 ", "", 5, "mr-1"],
              ordering: "future",
            },
            {
              category_id: " ",
              label: "Bad",
              asset_ids: ["mr-2"],
              ordering: "theme",
            },
          ],
          ordering: "future",
          stability_bound: "3",
        }),
        { status: 200 },
      ),
    );

    await expect(listPersonalSpaceCategories()).resolves.toEqual({
      categories: [
        {
          category_id: "cat-1",
          label: "Philosophy",
          asset_ids: ["mr-1"],
          ordering: "recency",
        },
      ],
      ordering: "recency",
      stability_bound: 0,
    });
  });

  it("dedupes duplicate personal-space category ids after trimming", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          categories: [
            {
              category_id: " cat-dup ",
              label: "First category",
              asset_ids: ["asset-1"],
              ordering: "theme",
            },
            {
              category_id: "cat-dup",
              label: "Duplicate category",
              asset_ids: ["asset-2"],
              ordering: "theme",
            },
            {
              category_id: "cat-other",
              label: "Other category",
              asset_ids: ["asset-other"],
              ordering: "theme",
            },
          ],
          ordering: "theme",
          stability_bound: 4,
        }),
        { status: 200 },
      ),
    );

    await expect(listPersonalSpaceCategories()).resolves.toEqual({
      categories: [
        {
          category_id: "cat-dup",
          label: "First category",
          asset_ids: ["asset-1"],
          ordering: "theme",
        },
        {
          category_id: "cat-other",
          label: "Other category",
          asset_ids: ["asset-other"],
          ordering: "theme",
        },
      ],
      ordering: "theme",
      stability_bound: 4,
    });
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

    const result = await getFileSuggestion(" doc with space ");

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(apiFetchMock.mock.calls[0][0]).toBe(
      "/api/meta-readings/file-suggestion?document_id=doc+with+space",
    );
    expect(result).toEqual(suggestionResponse);
  });

  it("sanitizes filing suggestions before they reach personal-space state", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          document_id: "  doc-1  ",
          matches: [
            {
              investigation_id: " inv-1 ",
              question: " q ",
              score: 0.72,
            },
            {
              investigation_id: " ",
              question: "bad",
              score: 1,
            },
            {
              investigation_id: "inv-2",
              question: "q2",
              score: "0.5",
            },
            {
              investigation_id: " inv-1 ",
              question: "duplicate q",
              score: 0.9,
            },
          ],
        }),
        { status: 200 },
      ),
    );

    await expect(getFileSuggestion("doc-1")).resolves.toEqual({
      document_id: "doc-1",
      matches: [
        {
          investigation_id: "inv-1",
          question: "q",
          score: 0.72,
        },
        {
          investigation_id: "inv-2",
          question: "q2",
          score: 0,
        },
      ],
    });
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

    await expect(getFileSuggestion(" doc-1 ")).resolves.toEqual({
      document_id: "doc-1",
      matches: [],
    });
  });

  it("rejects blank filing suggestion document ids before sending", async () => {
    await expect(getFileSuggestion(" ")).rejects.toThrow(/documentId/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("keeps unexpected suggestion failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(getFileSuggestion("doc-1")).rejects.toThrow(
      "GET /meta-readings/file-suggestion: HTTP 500",
    );
  });
});
