// SPR-05 / M2 — Voice-note recording primitive for anchored notes.
//
// REUSES Sprint 13's MediaRecorder + opus/webm capture pattern from
// components/InterviewVoiceCapture.tsx. We do NOT invent a new audio
// pipeline (per SPR-05 rigor #4 — Sprint 13's recorder + transcription
// path are dependencies, not in-scope rewrites). This file isolates
// the MediaRecorder state-machine into a hook so VoiceAnchor.tsx can
// render its own UI on top.
//
// What's different from InterviewVoiceCapture:
//   - This hook does NOT upload anywhere on stop — the caller
//     receives the audio Blob and decides what to do with it
//     (anchored save goes through apps/reading/api/voice/anchor.ts).
//   - It also exposes a live amplitude sample for the waveform
//     widget (M2 acceptance criterion: "live waveform renders
//     during recording").
//   - Consent is acquired implicitly on the first ``start()`` call;
//     the calling UI surfaces the permission denial.

import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceRecorderState =
  | "idle"
  | "requesting_consent"
  | "recording"
  | "stopped"
  | "error";

export interface VoiceRecorderHook {
  state: VoiceRecorderState;
  /** Duration in seconds (rounded to integer; ticks every 250ms). */
  durationSeconds: number;
  /** Live amplitude sample in [0, 1] — the waveform widget reads
   *  this. Computed from an AnalyserNode RMS over the last 256
   *  samples. */
  amplitude: number;
  error: string | null;
  /** The captured blob, available after ``stop()`` resolves and
   *  before the next ``start()``. Null while recording / idle. */
  audioBlob: Blob | null;
  start: () => Promise<void>;
  stop: () => Promise<Blob | null>;
  /** Releases any held MediaStream. Idempotent. */
  cleanup: () => void;
}

const RECORDER_MIME = "audio/webm;codecs=opus";
const CHUNK_TIMESLICE_MS = 200; // matches InterviewVoiceCapture
const FFT_SIZE = 256;

export function useVoiceRecorder(): VoiceRecorderHook {
  const [state, setState] = useState<VoiceRecorderState>("idle");
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [amplitude, setAmplitude] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const amplitudeRafRef = useRef<number | null>(null);

  const cleanup = useCallback(() => {
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (amplitudeRafRef.current !== null) {
      window.cancelAnimationFrame(amplitudeRafRef.current);
      amplitudeRafRef.current = null;
    }
    if (recorderRef.current) {
      try {
        if (recorderRef.current.state !== "inactive") {
          recorderRef.current.stop();
        }
      } catch {
        /* already stopped */
      }
      recorderRef.current = null;
    }
    if (audioCtxRef.current) {
      try {
        void audioCtxRef.current.close();
      } catch {
        /* ignore */
      }
      audioCtxRef.current = null;
      analyserRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  const start = useCallback(async () => {
    setError(null);
    setAudioBlob(null);
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

      // Amplitude tap — feeds the waveform display.
      try {
        const ctx = new AudioContext();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = FFT_SIZE;
        const source = ctx.createMediaStreamSource(stream);
        source.connect(analyser);
        audioCtxRef.current = ctx;
        analyserRef.current = analyser;
        const buf = new Uint8Array(analyser.fftSize);
        const tickAmplitude = () => {
          if (!analyserRef.current) return;
          analyserRef.current.getByteTimeDomainData(buf);
          // RMS in [0, 1]
          let sumSq = 0;
          for (let i = 0; i < buf.length; i++) {
            const v = (buf[i] - 128) / 128;
            sumSq += v * v;
          }
          setAmplitude(Math.min(1, Math.sqrt(sumSq / buf.length) * 3));
          amplitudeRafRef.current =
            window.requestAnimationFrame(tickAmplitude);
        };
        amplitudeRafRef.current =
          window.requestAnimationFrame(tickAmplitude);
      } catch {
        // AudioContext failure is non-fatal — recording proceeds
        // without the live waveform.
      }

      chunksRef.current = [];
      const rec = new MediaRecorder(stream, { mimeType: RECORDER_MIME });
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onerror = (e: Event) => {
        setError(
          `MediaRecorder error: ${(e as ErrorEvent).message ?? "unknown"}`,
        );
        setState("error");
      };
      rec.start(CHUNK_TIMESLICE_MS);
      recorderRef.current = rec;
      startTimeRef.current = Date.now();
      setDurationSeconds(0);
      tickRef.current = window.setInterval(() => {
        setDurationSeconds(
          Math.floor((Date.now() - startTimeRef.current) / 1000),
        );
      }, 250);
      setState("recording");
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? `Mic permission denied: ${e.message}`
          : "Mic permission denied.",
      );
      setState("error");
    }
  }, []);

  const stop = useCallback(async (): Promise<Blob | null> => {
    const rec = recorderRef.current;
    if (!rec || rec.state === "inactive") {
      setState("stopped");
      return audioBlob;
    }
    // Wait for the final ondataavailable to flush (MediaRecorder
    // dispatches one final chunk on stop). Resolve on onstop.
    const finished = new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
    });
    rec.stop();
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (amplitudeRafRef.current !== null) {
      window.cancelAnimationFrame(amplitudeRafRef.current);
      amplitudeRafRef.current = null;
    }
    await finished;
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    setAudioBlob(blob);
    setState("stopped");
    // Release the mic stream + analyser — the blob is in memory now.
    if (audioCtxRef.current) {
      try {
        void audioCtxRef.current.close();
      } catch {
        /* ignore */
      }
      audioCtxRef.current = null;
      analyserRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    recorderRef.current = null;
    return blob;
  }, [audioBlob]);

  return {
    state,
    durationSeconds,
    amplitude,
    error,
    audioBlob,
    start,
    stop,
    cleanup,
  };
}

/**
 * Visual waveform stripe driven by the hook's amplitude sample. A
 * deliberately simple bar — recording UIs that need a full FFT
 * histogram can compose the analyser node directly. This widget
 * trades fidelity for zero added bundle weight.
 */
export function VoiceWaveform({
  amplitude,
  recording,
}: {
  amplitude: number; // [0, 1]
  recording: boolean;
}) {
  // Render 16 bars; height interpolates between idle baseline (10%)
  // and current amplitude. Stagger with a sine offset so the bars
  // don't move in lock-step.
  const bars = Array.from({ length: 16 }, (_, i) => {
    const offset = Math.sin((Date.now() / 200 + i) * 0.6) * 0.2;
    const h = recording
      ? Math.min(1, 0.1 + amplitude * (0.9 + offset))
      : 0.1;
    return h;
  });
  return (
    <div
      className="flex items-center gap-[2px] h-6"
      aria-hidden="true"
      data-testid="voice-waveform"
    >
      {bars.map((h, i) => (
        <div
          key={i}
          style={{ height: `${Math.round(h * 100)}%` }}
          className={
            "w-[3px] rounded-sm " +
            (recording ? "bg-rose-500" : "bg-stone-400")
          }
        />
      ))}
    </div>
  );
}
