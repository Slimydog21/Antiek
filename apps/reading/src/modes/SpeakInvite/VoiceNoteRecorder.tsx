import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../../lib/api";

/**
 * Speak SPR-02 — the invitee's voice-note recorder (the literal
 * "voice-note" in "async voice-note interview").
 *
 * Records with MediaRecorder, posts the audio to the token-gated
 * /speak/invite/{token}/transcribe endpoint (reuses WhisperTranscriber
 * server-side), and hands the RAW transcript back to the caller via
 * `onTranscript`. The caller drops it into the answer box, where the
 * invitee CORRECTS it before sending — so distillation runs on the
 * corrected text, never the raw one (SPR-02 M5).
 *
 * Honest failure modes, all surfaced (never a silent distill of bad
 * audio): mic-denied → clear message; transcription unconfigured (503)
 * → "type instead"; transcription failed (422) → retry/type. The text
 * box is always available, so voice is an enhancement, never a gate.
 */
type State =
  | "idle"
  | "requesting_mic"
  | "recording"
  | "transcribing"
  | "done"
  | "mic_denied"
  | "unconfigured"
  | "error";

interface Props {
  token: string;
  onTranscript: (text: string) => void;
}

export default function VoiceNoteRecorder({ token, onTranscript }: Props) {
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<number | null>(null);
  const startedRef = useRef(0);

  const cleanup = useCallback(() => {
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    recorderRef.current = null;
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  const start = useCallback(async () => {
    setError(null);
    setState("requesting_mic");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      chunksRef.current = [];
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.start(200);
      recorderRef.current = rec;
      startedRef.current = Date.now();
      setSeconds(0);
      tickRef.current = window.setInterval(
        () => setSeconds(Math.floor((Date.now() - startedRef.current) / 1000)),
        250,
      );
      setState("recording");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Microphone access was denied.");
      setState("mic_denied");
    }
  }, []);

  const stopAndTranscribe = useCallback(async () => {
    const rec = recorderRef.current;
    if (!rec) return;
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    setState("transcribing");
    // Wait for the final ondataavailable flush after stop().
    await new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
      rec.stop();
    });
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    recorderRef.current = null;

    try {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      const resp = await apiFetch(`/speak/invite/${encodeURIComponent(token)}/transcribe`, {
        method: "POST",
        headers: { "Content-Type": "audio/webm" },
        body: blob,
      });
      if (resp.status === 503) {
        setState("unconfigured");
        return;
      }
      if (!resp.ok) {
        setError(`Couldn't transcribe (HTTP ${resp.status}). You can type your answer instead.`);
        setState("error");
        return;
      }
      const data = await resp.json();
      onTranscript(String(data.transcript ?? ""));
      setState("done");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }, [token, onTranscript]);

  return (
    <div className="mb-2">
      {state === "idle" || state === "done" ? (
        <button
          type="button"
          onClick={() => void start()}
          className="font-mono text-[11px] px-3 py-1 border border-ink-mute rounded text-sun-deep dark:text-sun hover:underline"
        >
          {state === "done" ? "record again" : "🎙 record instead of typing"}
        </button>
      ) : state === "requesting_mic" ? (
        <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">requesting microphone…</span>
      ) : state === "recording" ? (
        <button
          type="button"
          onClick={() => void stopAndTranscribe()}
          className="font-mono text-[11px] px-3 py-1 border-2 border-emperor rounded text-emperor hover:underline"
        >
          ⏹ stop &amp; transcribe · {seconds}s
        </button>
      ) : state === "transcribing" ? (
        <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">transcribing…</span>
      ) : null}

      {state === "done" && (
        <p className="font-mono text-[10px] text-aurora mt-1">
          Transcribed into the box below — please read it over and fix anything
          before you send (it's worth getting names and dates right).
        </p>
      )}
      {state === "unconfigured" && (
        <p className="font-mono text-[10px] text-warning dark:text-sun mt-1">
          Voice transcription isn't set up yet — please type your answer below.
        </p>
      )}
      {state === "mic_denied" && (
        <p className="font-mono text-[10px] text-emperor mt-1">
          Microphone access was denied. You can type your answer below instead.
        </p>
      )}
      {state === "error" && (
        <p className="font-mono text-[10px] text-emperor mt-1">{error}</p>
      )}
    </div>
  );
}
