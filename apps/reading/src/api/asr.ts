/**
 * Shared ASR (speech-in) service client — Living Roadmap SPR-14 M1.
 *
 * One thin client for the speech-in service: POST audio bytes →
 * `{transcript, language, duration_seconds}`. This RE-HOMES the existing
 * `transcribeAudio` (apps/reading/src/api/books.ts:97) against the SAME live
 * route `interfaces/research/api/read_voice.py` mounts at `POST
 * /voice/transcribe`, so the capture path becomes host-agnostic (any surface
 * can call it, not just the Reading book reader).
 *
 * HONESTY (SPR-14 rigor #1): the route is genuinely LIVE today, backed by
 * **Whisper-1** (`acquisition/voice/client.py:WhisperTranscriber`), NOT
 * MiMo-V2.5-ASR. MiMo-V2.5-ASR is the *intended future* backend behind the
 * SAME route — a backend swap (`Transcriber` is an injected Protocol), no new
 * route and no new credential mechanism. This client targets the route, so it
 * needs no change when the backend swaps. See
 * `docs/decisions/voice-infrastructure.md`.
 *
 * The §16 carve-out: ASR is a specialized SERVICE Antiek calls over the
 * network (a 503 when the operator key is absent is honest, never a
 * fabricated transcript) — it is not a self-hosted model and not a second
 * runtime. See the decision doc.
 *
 * This module does NOT persist anything. Persistence of the capture (the
 * transcript + audio reference + the user-sourced provenance label) flows
 * through the single-writer typed-event funnel in `useVoiceCapture`
 * (`postTypedEvent` → `/events/typed`), never a side store.
 */

import { API_BASE, apiFetch } from "../lib/api";

/** Normalized transcription response from `POST /voice/transcribe`. Field
 * names mirror the backend `TranscribeResponse` (read_voice.py). */
export interface TranscriptionResult {
  transcript: string;
  language: string | null;
  durationSeconds: number;
}

/** Why a transcription attempt failed — surfaced so a caller can choose to
 * retry vs. let the user type, and so a 503 is NEVER mistaken for an empty
 * transcript (SPR-14 rigor #3: a failed transcription is surfaced, never
 * persisted as a fake/empty transcript). */
export type AsrFailureKind =
  | "unavailable" // 503 — the ASR service (operator key / endpoint) is down
  | "empty_audio" // 400 — no audio bytes were sent
  | "timeout" // the request was aborted on the client timeout
  | "http"; // any other non-OK status

export class AsrError extends Error {
  constructor(
    public readonly kind: AsrFailureKind,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "AsrError";
  }
}

/** Default client-side timeout. Whisper can take ~60s on a long clip
 * (`acquisition/voice/client.py:DEFAULT_TIMEOUT_S = 120`); we give the
 * round-trip headroom past that so a slow-but-succeeding transcription is not
 * aborted, while a truly hung request still surfaces rather than hanging the
 * UI forever. */
export const DEFAULT_ASR_TIMEOUT_MS = 130_000;

/**
 * Transcribe a captured audio blob via the live `/voice/transcribe` route.
 *
 * Failure is surfaced as a typed {@link AsrError} (never a fabricated
 * transcript): 503 → `unavailable`, 400 → `empty_audio`, an aborted request
 * → `timeout`, any other non-OK → `http`. The caller (`useVoiceCapture`)
 * turns these into a user-visible error and persists NOTHING — there is no
 * `voice.captured` event for a failed transcription.
 */
export async function transcribe(
  audio: Blob,
  opts?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<TranscriptionResult> {
  const timeoutMs = opts?.timeoutMs ?? DEFAULT_ASR_TIMEOUT_MS;
  // Compose the caller's signal (if any) with a timeout abort.
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), timeoutMs);
  const onCallerAbort = () => timeoutController.abort();
  if (opts?.signal) {
    if (opts.signal.aborted) timeoutController.abort();
    else opts.signal.addEventListener("abort", onCallerAbort, { once: true });
  }

  let resp: Response;
  try {
    resp = await apiFetch(`${API_BASE}/voice/transcribe`, {
      method: "POST",
      headers: { "Content-Type": audio.type || "audio/webm" },
      body: audio,
      signal: timeoutController.signal,
    });
  } catch (e: unknown) {
    // An AbortError is the timeout (or a caller abort) — surface it as such.
    if ((e as { name?: string })?.name === "AbortError") {
      throw new AsrError("timeout", "Transcription timed out — try again.");
    }
    throw new AsrError("http", e instanceof Error ? e.message : String(e));
  } finally {
    clearTimeout(timer);
    opts?.signal?.removeEventListener("abort", onCallerAbort);
  }

  if (resp.status === 503) {
    throw new AsrError(
      "unavailable",
      "Transcription isn’t available right now.",
      503,
    );
  }
  if (resp.status === 400) {
    throw new AsrError("empty_audio", "No audio captured.", 400);
  }
  if (!resp.ok) {
    throw new AsrError("http", `POST /voice/transcribe: HTTP ${resp.status}`, resp.status);
  }

  const body = (await resp.json()) as {
    transcript: string;
    language: string | null;
    duration_seconds: number;
  };
  return {
    transcript: body.transcript,
    language: body.language,
    durationSeconds: body.duration_seconds,
  };
}
