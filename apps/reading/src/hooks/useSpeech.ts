import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE, apiFetch } from "../lib/api";

/**
 * useSpeech (Read SPR-07) — synthesize a reply to audio and play it.
 *
 * Backs the conversational rabbit hole's audio option: an AI reply that
 * is text can also be spoken. Calls POST /speech/tts (gated on the
 * operator key server-side), plays the returned mp3, and exposes a small
 * state machine so the UI can show loading / playing / error and a stop
 * control. This is the async reply path — not real-time talk-to-book,
 * which stays gated on round-trip latency.
 */

export type SpeechState = "idle" | "loading" | "playing" | "error";

export interface UseSpeech {
  state: SpeechState;
  error: string | null;
  /** Synthesize + play `text`. Stops any in-flight playback first. */
  speak: (text: string, voice?: string) => Promise<void>;
  stop: () => void;
}

export function useSpeech(): UseSpeech {
  const [state, setState] = useState<SpeechState>("idle");
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    cleanup();
    setState("idle");
  }, [cleanup]);

  const speak = useCallback(
    async (text: string, voice?: string) => {
      cleanup();
      if (!text.trim()) return;
      setState("loading");
      setError(null);
      try {
        const resp = await apiFetch(`${API_BASE}/speech/tts`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, voice }),
        });
        if (resp.status === 503) {
          throw new Error("Voice replies aren’t available right now.");
        }
        if (!resp.ok) {
          throw new Error(`TTS failed: HTTP ${resp.status}`);
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => setState("idle");
        audio.onerror = () => {
          setError("Playback failed.");
          setState("error");
        };
        await audio.play();
        setState("playing");
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
        setState("error");
      }
    },
    [cleanup],
  );

  // Revoke any object URL + stop audio on unmount.
  useEffect(() => cleanup, [cleanup]);

  return { state, error, speak, stop };
}
