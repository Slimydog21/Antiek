import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../lib/api";
import { emitWernerExperience } from "../werner/reactionBus";

/**
 * Browser-side voice capture for Speak invitees (master-spec
 * §11.5 + Product Depth SPR-08 M3).
 *
 * Substrate-first: capture happens entirely in MediaRecorder + an
 * uploadable Blob. No WebRTC peer-to-peer signaling is needed since
 * the substrate is a server-side aggregator, not a real-time call.
 * The component:
 *
 *   1. Starts a MediaRecorder bound to the user's microphone (16kHz
 *      mono opus inside webm) once the operator clicks 'Start'.
 *   2. Streams chunks as ondataavailable fires (~200ms intervals).
 *   3. Posts the accumulated Blob to the caller-provided upload route
 *      when the invitee clicks 'Stop'.
 *
 * Consent gate (§11.5 binding): the operator must explicitly grant
 * mic access. The component shows a clear state-machine that mirrors
 * the substrate state machine (idle → consent_granted → recording →
 * uploading → uploaded | error).
 *
 * The component does NOT render the interview transcript itself —
 * the orchestrator displays that downstream. This component owns
 * capture + upload only.
 */

type CaptureState =
  | "idle"
  | "requesting_consent"
  | "consent_granted"
  | "recording"
  | "uploading"
  | "uploaded"
  | "error";

interface Props {
  onUploaded?: (audioUrl: string) => void;
  /**
   * Build the upload URL from the captured duration. The Speak invitee surface
   * targets the TOKEN-gated route (``/speak/invite/{token}/voice``), so a
   * non-power-user's recording goes
   * through the same single voice owner without an operator session — no
   * second pipeline (Product Depth SPR-08 M3).
   */
  buildUploadUrl: (durationSeconds: number) => string;
  /** Called when the upload comes back non-OK, so the host can show an honest,
   *  reason-carrying failure (e.g. AIActionFailure on a no-key 503) instead of
   *  the generic inline error. */
  onUploadError?: (status: number, detail: string) => void;
}

export default function InterviewVoiceCapture({
  onUploaded,
  buildUploadUrl,
  onUploadError,
}: Props) {
  const [state, setState] = useState<CaptureState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [durationSeconds, setDurationSeconds] = useState<number>(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);

  const cleanup = useCallback(() => {
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (mediaRecorderRef.current) {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // already stopped — ignore
      }
      mediaRecorderRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  const requestConsent = async () => {
    setError(null);
    setState("requesting_consent");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16_000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;
      setState("consent_granted");
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? `Mic permission denied: ${e.message}`
          : "Mic permission denied.",
      );
      setState("error");
    }
  };

  const startRecording = () => {
    if (!streamRef.current) {
      setError("No mic stream — grant consent first.");
      setState("error");
      return;
    }
    chunksRef.current = [];
    const rec = new MediaRecorder(streamRef.current, {
      mimeType: "audio/webm;codecs=opus",
    });
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    rec.onerror = (e: Event) => {
      setError(`MediaRecorder error: ${(e as ErrorEvent).message ?? "unknown"}`);
      setState("error");
    };
    rec.start(200); // 200ms chunk timeslice
    mediaRecorderRef.current = rec;
    startTimeRef.current = Date.now();
    setDurationSeconds(0);
    tickRef.current = window.setInterval(() => {
      setDurationSeconds(
        Math.floor((Date.now() - startTimeRef.current) / 1000),
      );
    }, 250);
    setState("recording");
  };

  const stopAndUpload = async () => {
    if (!mediaRecorderRef.current) return;
    mediaRecorderRef.current.stop();
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    setState("uploading");

    // Wait for the final ondataavailable to fire (MediaRecorder
    // flushes on stop). One requestAnimationFrame is enough in
    // practice; tests on slower hardware may need a microtask delay.
    await new Promise((r) => requestAnimationFrame(r));

    try {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      // Raw-body upload; duration rides on the query string. Keeps
      // the substrate side free of the python-multipart dependency
      // for a single-field upload (master-spec §11.5). The URL is
      // pluggable so the token-gated invitee route can be targeted
      // without forking the capture component (SPR-08 M3).
      const url = buildUploadUrl(durationSeconds);
      const resp = await apiFetch(url, {
        method: "POST",
        headers: { "Content-Type": "audio/webm" },
        body: blob,
      });
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try {
          const body = await resp.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          // keep the status-only detail
        }
        if (onUploadError) onUploadError(resp.status, detail);
        throw new Error(`Upload failed: ${detail}`);
      }
      const data = await resp.json();
      setState("uploaded");
      emitWernerExperience("note_saved");
      if (data.audio_url && onUploaded) {
        onUploaded(data.audio_url);
      } else if (onUploaded) {
        // The token-gated route returns the transcript, not an audio_url; still
        // signal completion so the invitee surface can advance.
        onUploaded(typeof data.transcript === "string" ? data.transcript : "");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setState("error");
      emitWernerExperience("fail");
    } finally {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      mediaRecorderRef.current = null;
    }
  };

  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-serif text-ink dark:text-bright">Voice capture</p>
        <span className="text-[11px] font-mono text-shadow-1 dark:text-moonlight uppercase">
          {state.replace(/_/g, " ")}
        </span>
      </div>

      {state === "idle" && (
        <button
          type="button"
          onClick={requestConsent}
          className="px-3 py-1.5 rounded-md bg-ink text-white text-sm font-medium hover:bg-shadow-2 transition-colors"
        >
          Grant mic access
        </button>
      )}

      {state === "consent_granted" && (
        <button
          type="button"
          onClick={startRecording}
          className="px-3 py-1.5 rounded-md bg-rose-700 text-white text-sm font-medium hover:bg-rose-600 transition-colors"
        >
          Start recording
        </button>
      )}

      {state === "recording" && (
        <div className="space-y-2">
          <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
            Recording · {durationSeconds}s
          </p>
          <button
            type="button"
            onClick={stopAndUpload}
            className="px-3 py-1.5 rounded-md bg-shadow-2 text-white text-sm font-medium hover:bg-shadow-1 transition-colors"
          >
            Stop &amp; upload
          </button>
        </div>
      )}

      {state === "uploading" && (
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">Uploading…</p>
      )}

      {state === "uploaded" && (
        <p className="text-xs font-mono text-emerald-700">
          Upload complete · {durationSeconds}s of audio captured.
        </p>
      )}

      {state === "error" && (
        <p className="text-xs font-mono text-emperor">{error ?? "Unknown error."}</p>
      )}
    </div>
  );
}
