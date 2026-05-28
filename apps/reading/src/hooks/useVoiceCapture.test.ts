/**
 * useVoiceCapture.test.ts — Living Roadmap SPR-14 M1 + M3 (voice-in).
 *
 * Drives the shared capture hook through the four enumerated failure inputs
 * (rigor #3) plus the happy path, asserting:
 *   - capture → transcribe returns text + the USER-SOURCED label (M1/M3);
 *   - the persisted `voice.captured` event carries `source_kind: "user"` AND
 *     the audio_ref pointer (M1: blob persists by reference through the
 *     typed-event funnel, never a side store) (M3 distinguishability);
 *   - silent audio → blank transcript flagged "empty", NOT hallucinated;
 *   - very long audio → refused with a stated bound, not silently truncated;
 *   - transcription 503 → surfaced, NOTHING persisted (no event posted).
 *
 * The recorder is stubbed (no real mic), and `fetch` is stubbed so BOTH the
 * ASR call (`/voice/transcribe`) and the persist call (`/events/typed`) are
 * driven deterministically — this asserts the CLIENT SHAPE against a fixture,
 * NOT a live MiMo/Whisper round-trip (SPR-14 rigor #1).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useVoiceCapture, MAX_AUDIO_BYTES } from "./useVoiceCapture";

// ── Controllable fake recorder, installed over the real hook module ────────

let fakeBlob: Blob | null = null;
let fakeState = "idle";
const recorderStub = {
  get state() {
    return fakeState;
  },
  error: null as string | null,
  get blob() {
    return fakeBlob;
  },
  start: vi.fn(async () => {
    fakeState = "recording";
  }),
  stop: vi.fn(() => {
    fakeState = "stopped";
  }),
  reset: vi.fn(() => {
    fakeState = "idle";
    fakeBlob = null;
  }),
};

vi.mock("./useVoiceRecorder", () => ({
  useVoiceRecorder: () => recorderStub,
}));

// ── fetch fixture ──────────────────────────────────────────────────────────

interface FetchPlan {
  // by URL substring → response
  transcribe?: { status: number; body?: unknown };
  events?: { status: number; body?: unknown };
}

let plan: FetchPlan = {};
const fetchCalls: { url: string; init?: RequestInit }[] = [];

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

beforeEach(() => {
  fakeBlob = null;
  fakeState = "idle";
  plan = {};
  fetchCalls.length = 0;
  recorderStub.start.mockClear();
  recorderStub.stop.mockClear();
  recorderStub.reset.mockClear();

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    fetchCalls.push({ url, init });
    if (url.includes("/voice/transcribe")) {
      const r = plan.transcribe ?? { status: 200, body: { transcript: "hello", language: "en", duration_seconds: 1.2 } };
      return jsonResponse(r.status, r.body ?? {});
    }
    if (url.includes("/events/typed")) {
      const r = plan.events ?? { status: 200, body: { event_id: "evt-voice-1", action_type: "voice.captured" } };
      return jsonResponse(r.status, r.body ?? {});
    }
    throw new Error(`unexpected fetch to ${url}`);
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// A tiny non-empty blob with a known size.
function blobOf(bytes: number): Blob {
  return { size: bytes, type: "audio/webm" } as Blob;
}

// ── Happy path: text + user-sourced label + persisted event ────────────────

describe("useVoiceCapture — capture → transcribe → user-sourced (M1/M3)", () => {
  it("returns the transcript with sourceKind 'user' and persists a voice.captured event carrying source_kind 'user' + audio_ref", async () => {
    plan.transcribe = { status: 200, body: { transcript: "the mind is not a vessel", language: "en", duration_seconds: 2.0 } };
    plan.events = { status: 200, body: { event_id: "evt-9", action_type: "voice.captured" } };
    fakeBlob = blobOf(2048);

    const { result } = renderHook(() => useVoiceCapture());

    await act(async () => {
      await result.current.start();
    });

    let captured: Awaited<ReturnType<typeof result.current.stopAndCapture>> = null;
    await act(async () => {
      captured = await result.current.stopAndCapture({
        investigationId: "inv-1",
        documentId: "doc-book-1",
        audioRef: "blob://audio-123",
      });
    });

    // M1: text + the user-sourced provenance label on the returned result.
    expect(captured).not.toBeNull();
    expect(captured!.transcript).toBe("the mind is not a vessel");
    expect(captured!.sourceKind).toBe("user");
    expect(captured!.transcriptStatus).toBe("ok");
    expect(captured!.eventId).toBe("evt-9");
    expect(result.current.phase).toBe("captured");

    // M3: the PERSISTED event carries source_kind "user" (distinguishable
    // from a model-output node) + the audio_ref pointer (blob by reference).
    const persist = fetchCalls.find((c) => c.url.includes("/events/typed"));
    expect(persist).toBeDefined();
    const body = JSON.parse(persist!.init!.body as string);
    expect(body.payload.action_type).toBe("voice.captured");
    expect(body.payload.source_kind).toBe("user");
    expect(body.payload.transcript).toBe("the mind is not a vessel");
    expect(body.payload.audio_ref).toBe("blob://audio-123");
    expect(body.investigation_id).toBe("inv-1");
    expect(body.document_id).toBe("doc-book-1");
  });
});

// ── Rigor #3 (a): silent audio → blank, flagged, NOT hallucinated ──────────

describe("useVoiceCapture — silent audio (rigor #3a)", () => {
  it("keeps a blank transcript blank and flags it 'empty' — never invents text", async () => {
    plan.transcribe = { status: 200, body: { transcript: "   ", language: null, duration_seconds: 0.5 } };
    fakeBlob = blobOf(512);

    const { result } = renderHook(() => useVoiceCapture());
    await act(async () => { await result.current.start(); });

    let captured: Awaited<ReturnType<typeof result.current.stopAndCapture>> = null;
    await act(async () => {
      captured = await result.current.stopAndCapture({ investigationId: "inv-1" });
    });

    expect(captured).not.toBeNull();
    expect(captured!.transcript.trim()).toBe(""); // unchanged — no hallucination
    expect(captured!.transcriptStatus).toBe("empty");
    expect(captured!.sourceKind).toBe("user");
    // Still persisted (a real silent capture is a fact), with the empty flag.
    const persist = fetchCalls.find((c) => c.url.includes("/events/typed"));
    const body = JSON.parse(persist!.init!.body as string);
    expect(body.payload.transcript_status).toBe("empty");
  });
});

// ── Rigor #3 (b): very long audio → bounded, not silently truncated ─────────

describe("useVoiceCapture — very long audio (rigor #3b)", () => {
  it("refuses an over-cap recording with a stated bound and persists nothing", async () => {
    fakeBlob = blobOf(MAX_AUDIO_BYTES + 1);

    const { result } = renderHook(() => useVoiceCapture());
    await act(async () => { await result.current.start(); });

    let captured: Awaited<ReturnType<typeof result.current.stopAndCapture>> = null;
    await act(async () => {
      captured = await result.current.stopAndCapture({ investigationId: "inv-1" });
    });

    expect(captured).toBeNull();
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/shorter clip/i);
    // Not silently truncated AND not sent: no transcribe call, no persist.
    expect(fetchCalls.find((c) => c.url.includes("/voice/transcribe"))).toBeUndefined();
    expect(fetchCalls.find((c) => c.url.includes("/events/typed"))).toBeUndefined();
  });
});

// ── Rigor #3 (c): transcription failure → surfaced, NOTHING persisted ──────

describe("useVoiceCapture — transcription 503 (rigor #3c)", () => {
  it("surfaces a 503 and persists no voice.captured event (no fake transcript)", async () => {
    plan.transcribe = { status: 503, body: { detail: "transcription_unavailable" } };
    fakeBlob = blobOf(1024);

    const { result } = renderHook(() => useVoiceCapture());
    await act(async () => { await result.current.start(); });

    let captured: Awaited<ReturnType<typeof result.current.stopAndCapture>> = null;
    await act(async () => {
      captured = await result.current.stopAndCapture({ investigationId: "inv-1" });
    });

    expect(captured).toBeNull();
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/isn’t available|not available|unavailable/i);
    // The load-bearing assertion: a 503 NEVER becomes a persisted node.
    expect(fetchCalls.find((c) => c.url.includes("/events/typed"))).toBeUndefined();
  });
});
