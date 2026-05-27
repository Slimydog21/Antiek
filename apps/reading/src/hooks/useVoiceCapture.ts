import { useCallback, useState } from "react";

import { AsrError, transcribe } from "../api/asr";
import { postTypedEvent } from "../lib/api";
import { useVoiceRecorder, type RecorderState } from "./useVoiceRecorder";

/**
 * useVoiceCapture (Living Roadmap SPR-14 M1) — the ONE shared, host-agnostic
 * capture+transcribe hook every surface mounts (Research float-menu voice
 * SPR-04, voice prompt SPR-05, talk-to-book SPR-08, voice-to-draft SPR-09,
 * async interview SPR-10). It composes — it does NOT reinvent:
 *
 *   record  → `useVoiceRecorder`  (apps/reading/src/hooks/useVoiceRecorder.ts:21)
 *   transcribe → `api/asr.transcribe` (the LIVE `/voice/transcribe` route;
 *                Whisper today, MiMo-V2.5-ASR the intended future backend
 *                behind the same route — see docs/decisions/voice-infrastructure.md)
 *   persist → `postTypedEvent` → `/events/typed`  (single-writer funnel;
 *                NO client-side store of any kind — the audio blob persists
 *                by REFERENCE via `audio_ref`, the transcript via the event)
 *
 * PROVENANCE (SPR-14 M3 / master-spec §9): a voice capture is ALWAYS
 * `sourceKind: "user"` (human-authored). The persisted `voice.captured` event
 * pins `source_kind` to the literal "user" in the schema, so a voice
 * transcript node can NEVER be conflated with a model-output node in the one
 * graph — that conflation is a §9 violation. The TTS-out half (the other
 * builder) labels narration "ai"; "user" and "ai" are the SAME shared
 * `SourceKind` vocabulary, so a consumer distinguishes voice-in from model
 * output by one field.
 *
 * FAILURE INPUTS handled (SPR-14 rigor #3 — enumerated before coding):
 *   (a) silent audio  → no hallucinated transcript. A blank/whitespace
 *       transcript is kept blank and flagged `transcriptStatus: "empty"`,
 *       never invented text. (The reader confirms/corrects downstream, as
 *       VoiceNote.tsx already does — capture does not assert the words.)
 *   (b) very long audio → BOUNDED, not silently truncated. A recording past
 *       `MAX_AUDIO_BYTES` is refused with a clear `error` BEFORE the network
 *       call (so we neither drop it nor send a giant body that times out and
 *       looks like a failure); the user is told to record a shorter clip.
 *       The blob is left intact — nothing is silently cut.
 *   (c) transcription failure (503 / timeout / other) → surfaced as `error`,
 *       and NOTHING is persisted: there is no `voice.captured` event for a
 *       failed transcription (a 503 must never become a fabricated/empty
 *       transcript node).
 *   (d) §9.0 withheld region over TTS — handled by the voice-OUT half (the
 *       other builder's ReadAloud guard); out of scope for this capture hook.
 *
 * This hook is NOT mounted in any surface UI here — that is the consumers'
 * job (SPR-04/05/08/09/10).
 */

export type CapturePhase =
  | "idle"
  | "recording"
  | "transcribing"
  | "persisting"
  | "captured"
  | "error";

/** Upper bound on a single captured blob before we refuse + ask for a
 * shorter clip rather than silently truncate or send a body that hangs.
 * ~25 MB ≈ several minutes of webm/opus; deliberately generous but finite.
 * The bound is STATED (rigor #3 (b)) — a longer clip is refused with a clear
 * message, never dropped or cut. A future chunked-capture path can raise
 * this; until then the bound is honest. */
export const MAX_AUDIO_BYTES = 25 * 1024 * 1024;

/** The result of a successful capture — text + the user-sourced provenance
 * label + the persisted event id. `sourceKind` is fixed "user". */
export interface VoiceCaptureResult {
  transcript: string;
  language: string | null;
  durationSeconds: number;
  /** §9 provenance — ALWAYS "user" for a voice capture (human-authored). */
  sourceKind: "user";
  /** "ok" | "empty" (silent — blank transcript, NOT a hallucination). An
   * over-cap long clip is REFUSED (surfaced as an error, never persisted), so
   * it never reaches a status here — there is no "bounded". */
  transcriptStatus: "ok" | "empty";
  /** The id of the persisted `voice.captured` typed event (null only if
   * events are disabled server-side). */
  eventId: string | null;
}

export interface UseVoiceCapture {
  phase: CapturePhase;
  error: string | null;
  recorderState: RecorderState;
  result: VoiceCaptureResult | null;
  /** Begin recording. */
  start: () => Promise<void>;
  /** Stop recording, then transcribe + persist. Returns the result, or null
   * on failure (with `error` set). */
  stopAndCapture: (opts: CaptureOpts) => Promise<VoiceCaptureResult | null>;
  /** Reset to idle for another capture. */
  reset: () => void;
}

export interface CaptureOpts {
  investigationId: string;
  /** Optional document anchor (e.g. a book the capture is about). */
  documentId?: string;
  /** A reference to where the audio blob is persisted (object key / URL).
   * The blob itself is NOT inlined and NOT kept in a client store — the
   * event carries only this pointer. Consumers that have already uploaded
   * the blob pass its reference; capture-only consumers may omit it. */
  audioRef?: string | null;
  /** Optional role/policy hints threaded onto the typed event. */
  role?: string;
  policyId?: string;
}

function blobToStatus(text: string): "ok" | "empty" {
  return text.trim().length === 0 ? "empty" : "ok";
}

export function useVoiceCapture(): UseVoiceCapture {
  const recorder = useVoiceRecorder();
  const [phase, setPhase] = useState<CapturePhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VoiceCaptureResult | null>(null);

  const start = useCallback(async () => {
    setError(null);
    setResult(null);
    await recorder.start();
    // useVoiceRecorder surfaces a permission denial as state "denied" with a
    // message; reflect that rather than claiming we're recording.
    setPhase("recording");
  }, [recorder]);

  const stopAndCapture = useCallback(
    async (opts: CaptureOpts): Promise<VoiceCaptureResult | null> => {
      // Stop the recorder and wait for the blob. useVoiceRecorder finalizes
      // the blob asynchronously on MediaRecorder.onstop; poll its ref via a
      // microtask loop bounded by a short deadline so we don't hang if the
      // recorder never produced data.
      recorder.stop();
      const blob = await waitForBlob(() => recorder.blob);

      if (!blob || blob.size === 0) {
        setPhase("error");
        setError("No audio captured. Try recording again.");
        return null;
      }

      // (b) very long audio — bounded, not silently truncated.
      if (blob.size > MAX_AUDIO_BYTES) {
        setPhase("error");
        setError(
          "That recording is too long to transcribe in one piece — " +
            "please record a shorter clip.",
        );
        return null;
      }

      setPhase("transcribing");
      setError(null);

      let transcriptText: string;
      let language: string | null;
      let durationSeconds: number;
      try {
        const t = await transcribe(blob);
        transcriptText = t.transcript;
        language = t.language;
        durationSeconds = t.durationSeconds;
      } catch (e: unknown) {
        // (c) transcription failure — surfaced, NOTHING persisted.
        setPhase("error");
        if (e instanceof AsrError) {
          setError(e.message);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
        return null;
      }

      // (a) silent audio — keep the transcript blank, flag it; do NOT invent.
      const transcriptStatus = blobToStatus(transcriptText);

      setPhase("persisting");
      let eventId: string | null = null;
      try {
        const emitted = await postTypedEvent({
          investigation_id: opts.investigationId,
          document_id: opts.documentId,
          role: opts.role,
          policy_id: opts.policyId,
          payload: {
            action_type: "voice.captured",
            source_kind: "user",
            transcript: transcriptText,
            transcript_status: transcriptStatus,
            language,
            duration_seconds: durationSeconds,
            audio_ref: opts.audioRef ?? null,
          },
        });
        eventId = emitted.event_id;
      } catch (e: unknown) {
        // Transcription succeeded but persistence failed — surface it and do
        // not pretend the capture was stored. The transcript is still
        // returned (in the error path we return null; callers re-try persist
        // by re-capturing — the substrate is the source of truth, so an
        // un-persisted transcript is not a stored capture).
        setPhase("error");
        setError(
          "Captured the transcript but couldn’t save it — " +
            (e instanceof Error ? e.message : String(e)),
        );
        return null;
      }

      const captured: VoiceCaptureResult = {
        transcript: transcriptText,
        language,
        durationSeconds,
        sourceKind: "user",
        transcriptStatus,
        eventId,
      };
      setResult(captured);
      setPhase("captured");
      return captured;
    },
    [recorder],
  );

  const reset = useCallback(() => {
    recorder.reset();
    setPhase("idle");
    setError(null);
    setResult(null);
  }, [recorder]);

  return {
    phase,
    error,
    recorderState: recorder.state,
    result,
    start,
    stopAndCapture,
    reset,
  };
}

/** Poll a getter until it yields a non-null blob or a short deadline passes.
 * useVoiceRecorder finalizes its blob on MediaRecorder.onstop (a tick after
 * stop()); this bridges that gap without coupling to its internals. */
async function waitForBlob(
  get: () => Blob | null,
  deadlineMs = 5_000,
): Promise<Blob | null> {
  const start = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const b = get();
    if (b) return b;
    if (Date.now() - start > deadlineMs) return null;
    await new Promise((r) => setTimeout(r, 20));
  }
}
