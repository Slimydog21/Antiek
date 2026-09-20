import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useVoiceRecorder (Read SPR-06) — minimal MediaRecorder wrapper that
 * yields an audio Blob. Mic-permission-denied is surfaced as an error,
 * not a crash (the spec's M1 acceptance). Kept tiny + separate from the
 * transcribe/distill flow so the flow is testable without a real mic.
 */

export type RecorderState = "idle" | "recording" | "stopped" | "denied" | "error";

export interface UseVoiceRecorder {
  state: RecorderState;
  error: string | null;
  blob: Blob | null;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

export function useVoiceRecorder(): UseVoiceRecorder {
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const mountedRef = useRef(true);
  const startAttemptRef = useRef(0);

  const stopTracks = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const start = useCallback(async () => {
    const attempt = ++startAttemptRef.current;
    setError(null);
    setBlob(null);
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current || attempt !== startAttemptRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const rec = new MediaRecorder(stream);
      recorderRef.current = rec;
      rec.ondataavailable = (e: BlobEvent) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        if (mountedRef.current) {
          setBlob(new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" }));
          setState("stopped");
        }
        stopTracks();
      };
      rec.start();
      setState("recording");
    } catch (e: unknown) {
      if (!mountedRef.current || attempt !== startAttemptRef.current) return;
      stopTracks();
      // getUserMedia rejects with NotAllowedError on permission denial.
      const name = (e as { name?: string })?.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        setState("denied");
        setError("Microphone permission was denied. You can still type a note.");
      } else {
        setState("error");
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }, [stopTracks]);

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
  }, []);

  const reset = useCallback(() => {
    startAttemptRef.current += 1;
    setState("idle");
    setError(null);
    setBlob(null);
    chunksRef.current = [];
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      startAttemptRef.current += 1;
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop();
      } else {
        stopTracks();
      }
    };
  }, [stopTracks]);

  return { state, error, blob, start, stop, reset };
}
