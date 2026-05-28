/**
 * tts.test.ts — SPR-14 M2 + M3-voice-out.
 *
 * Verifies the read-aloud client SHAPE against a fixture. The real /speech/tts
 * route is live-when-keyed (OpenAITTSProvider.synthesize → OpenAI /v1/audio/
 * speech); a keyed live round-trip is not exercised here — see api/tts.ts
 * header. The load-bearing cases are the §9.0 withheld refusal (the TTS service
 * is NEVER called) and the degenerate-length bound; the happy path proves
 * text → audio Blob via the /speech/tts route (not the dispatch tier), and the
 * provenance assertion proves narration is labelled model-generated, distinct
 * from a user-sourced label.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the lib/api boundary: apiFetch (the /speech/tts network call) + getChunk
// (the §9.0 servability lookup). We do NOT edit lib/api — we import from it.
vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
  getChunk: vi.fn(),
}));

import { apiFetch, getChunk } from "../lib/api";
import {
  MAX_NARRATION_MINUTES,
  NARRATION_WPM,
  TTS_OUT_SOURCE_KIND,
  TtsError,
  narrate,
  narrationBudgetForMinutes,
  scopeNarrationText,
  synthesizeSpeech,
} from "./tts";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;
const mockGetChunk = getChunk as unknown as ReturnType<typeof vi.fn>;

// A recorded "audio" fixture — the bytes are opaque to the client (it returns a
// Blob the control plays). This stands in for the live MiMo-TTS round-trip.
const AUDIO_FIXTURE = new Blob([new Uint8Array([0x49, 0x44, 0x33])], {
  type: "audio/mpeg",
});

function okAudioResponse(): Response {
  return {
    ok: true,
    status: 200,
    blob: async () => AUDIO_FIXTURE,
  } as unknown as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
  mockGetChunk.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("synthesizeSpeech — text → audio via the tts tier (fixtured)", () => {
  it("plays audio for given text: POSTs to /speech/tts and returns the Blob", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());

    const blob = await synthesizeSpeech("Hello, reader.");

    expect(blob).toBe(AUDIO_FIXTURE);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/speech/tts");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toMatchObject({ text: "Hello, reader." });
  });

  it("empty / whitespace text is a no-op-not-a-crash: throws TtsError(empty) BEFORE any network call", async () => {
    await expect(synthesizeSpeech("   ")).rejects.toMatchObject({ kind: "empty" });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("a 503 from the (stubbed) provider surfaces as unavailable, not a silent failure", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 503 } as unknown as Response);
    await expect(synthesizeSpeech("anything")).rejects.toMatchObject({
      kind: "unavailable",
    });
  });

  it("any other non-ok response surfaces as a network TtsError", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 500 } as unknown as Response);
    await expect(synthesizeSpeech("anything")).rejects.toMatchObject({ kind: "network" });
  });
});

describe("length/time box — how X minutes maps to narration scope", () => {
  it("maps minutes → word budget at NARRATION_WPM", () => {
    expect(narrationBudgetForMinutes(2)).toEqual({
      minutes: 2,
      wordBudget: 2 * NARRATION_WPM,
    });
  });

  it("scopes a too-long explanation to the word budget (whole words, no mid-word cut)", () => {
    const budget = narrationBudgetForMinutes(1); // NARRATION_WPM words
    const longText = Array.from({ length: NARRATION_WPM + 50 }, (_, i) => `w${i}`).join(" ");
    const scoped = scopeNarrationText(longText, budget);
    expect(scoped.split(/\s+/)).toHaveLength(NARRATION_WPM);
    expect(scoped.endsWith(`w${NARRATION_WPM - 1}`)).toBe(true);
  });

  it("leaves a short explanation untouched (does not pad)", () => {
    const budget = narrationBudgetForMinutes(10);
    expect(scopeNarrationText("just three words", budget)).toBe("just three words");
  });

  describe("degenerate length — stated bound, not silent (rigor #3)", () => {
    it("rejects 0 minutes", () => {
      expect(() => narrationBudgetForMinutes(0)).toThrow(TtsError);
      expect(() => narrationBudgetForMinutes(0)).toThrowError(/at least/);
    });
    it("rejects a negative request", () => {
      expect(() => narrationBudgetForMinutes(-5)).toThrow(TtsError);
    });
    it("rejects a non-finite request", () => {
      expect(() => narrationBudgetForMinutes(Number.POSITIVE_INFINITY)).toThrow(TtsError);
      expect(() => narrationBudgetForMinutes(NaN)).toThrow(TtsError);
    });
    it("rejects an absurdly-large request above the cap, naming the cap", () => {
      expect(() => narrationBudgetForMinutes(MAX_NARRATION_MINUTES + 1)).toThrowError(
        new RegExp(String(MAX_NARRATION_MINUTES)),
      );
    });
  });
});

describe("narrate — the one entry point (§9.0 + length + provenance)", () => {
  it("LOAD-BEARING §9.0: a withheld chunk (servable=false) is refused and the TTS service is NEVER called", async () => {
    mockGetChunk.mockResolvedValue({ chunk_id: "c1", servable: false } as never);

    await expect(narrate("secret body text", { chunkId: "c1" })).rejects.toMatchObject({
      kind: "withheld",
    });

    // The body never reached the network — the service was not called at all.
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("a servable chunk narrates and the text reaches the service", async () => {
    mockGetChunk.mockResolvedValue({ chunk_id: "c2", servable: true } as never);
    mockFetch.mockResolvedValue(okAudioResponse());

    const result = await narrate("model wrote this", { chunkId: "c2" });

    expect(result.audio).toBe(AUDIO_FIXTURE);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(JSON.parse(mockFetch.mock.calls[0][1]?.body as string).text).toBe(
      "model wrote this",
    );
  });

  it("§9.0 is enforced BEFORE length scoping (a withheld + bad-length request still refuses, never narrates)", async () => {
    mockGetChunk.mockResolvedValue({ chunk_id: "c3", servable: false } as never);
    await expect(narrate("body", { chunkId: "c3", minutes: 0 })).rejects.toMatchObject({
      kind: "withheld",
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("an X-minute request produces a correspondingly-scoped narration (text trimmed to the budget)", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());
    const longText = Array.from({ length: 400 }, (_, i) => `w${i}`).join(" ");

    const result = await narrate(longText, { minutes: 1 }); // 1 min → NARRATION_WPM words

    expect(result.budget?.wordBudget).toBe(NARRATION_WPM);
    expect(result.spokenText.split(/\s+/)).toHaveLength(NARRATION_WPM);
    // Only the scoped text reached the service, not the full 400 words.
    expect(JSON.parse(mockFetch.mock.calls[0][1]?.body as string).text).toBe(
      result.spokenText,
    );
  });

  it("PROVENANCE: TTS-out is labelled model-generated ('ai'), distinct from a user-sourced label", async () => {
    mockFetch.mockResolvedValue(okAudioResponse());

    const result = await narrate("a model sentence");

    expect(result.sourceKind).toBe(TTS_OUT_SOURCE_KIND);
    expect(result.sourceKind).toBe("ai");
    // It is NOT user-sourced — the read-aloud path creates no user node.
    expect(result.sourceKind).not.toBe("user");
  });

  it("a degenerate length throws before synthesis (no service call)", async () => {
    await expect(narrate("text", { minutes: 0 })).rejects.toMatchObject({
      kind: "degenerate_length",
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
