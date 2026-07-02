import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", () => ({
  API_BASE: "/api",
  apiFetch: apiFetchMock,
}));

import { transcribe, uploadVoiceBlob } from "./asr";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => {
  apiFetchMock.mockReset();
});

describe("asr api — transcription boundary", () => {
  it("posts audio to the shared transcription route and sanitizes the response", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        transcript: "  spoken words  ",
        language: "  en  ",
        duration_seconds: "3",
      }),
    );
    const audio = new Blob(["audio"], { type: "audio/ogg" });

    const result = await transcribe(audio);

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/voice/transcribe");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "audio/ogg" });
    expect(init.body).toBe(audio);
    expect(result).toEqual({
      transcript: "spoken words",
      language: "en",
      durationSeconds: 0,
    });
  });

  it("keeps blank transcripts valid so silence is flagged downstream, not fabricated", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse(200, { transcript: "   ", language: null, duration_seconds: 0.5 }),
    );

    await expect(transcribe(new Blob(["audio"]))).resolves.toEqual({
      transcript: "",
      language: null,
      durationSeconds: 0.5,
    });
  });

  it("rejects malformed successful transcription responses as typed ASR failures", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse(200, { transcript: null, language: "en", duration_seconds: 1 }),
    );

    await expect(transcribe(new Blob(["audio"]))).rejects.toMatchObject({
      name: "AsrError",
      kind: "http",
      status: 200,
      message: "Malformed transcription response.",
    });
  });

  it("surfaces route failures with typed ASR kinds", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no key", { status: 503 }));
    await expect(transcribe(new Blob(["audio"]))).rejects.toMatchObject({
      kind: "unavailable",
    });

    apiFetchMock.mockResolvedValueOnce(new Response("empty", { status: 400 }));
    await expect(transcribe(new Blob(["audio"]))).rejects.toMatchObject({
      kind: "empty_audio",
    });

    apiFetchMock.mockResolvedValueOnce(new Response("large", { status: 413 }));
    await expect(transcribe(new Blob(["audio"]))).rejects.toMatchObject({
      kind: "too_large",
    });
  });
});

describe("asr api — voice blob boundary", () => {
  it("uploads audio blobs and sanitizes the persisted audio reference", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        audio_ref: "  voice-blob://sha256/abc.webm  ",
        byte_size: 2048,
        sha256: "  abc  ",
      }),
    );
    const audio = new Blob(["audio"]);

    const result = await uploadVoiceBlob(audio);

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/voice/blob");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "audio/webm" });
    expect(init.body).toBe(audio);
    expect(result).toEqual({
      audioRef: "voice-blob://sha256/abc.webm",
      byteSize: 2048,
      sha256: "abc",
    });
  });

  it("rejects malformed successful blob responses before persistence can reference them", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        audio_ref: " ",
        byte_size: "2048",
        sha256: "abc",
      }),
    );

    await expect(uploadVoiceBlob(new Blob(["audio"]))).rejects.toMatchObject({
      name: "AsrError",
      kind: "http",
      status: 200,
      message: "Malformed voice-blob response.",
    });
  });
});
