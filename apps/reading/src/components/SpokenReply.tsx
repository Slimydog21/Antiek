import { useEffect } from "react";

import { useSpeech } from "../hooks/useSpeech";
import { emitWernerExperience } from "../werner/reactionBus";

/**
 * SpokenReply (Read SPR-07) — the audio half of the conversational
 * rabbit hole. Mounts beside an AI reply's text; a "Listen" control
 * speaks it. When `autoPlay` is set (the reader's reply-mode preference
 * is "audio"), it speaks on mount — so a reader who prefers audio hears
 * each reply without clicking. The text is always present too; voice is
 * an option layered on, never a replacement (text-note path stays
 * intact, per the spec's fairness rigor).
 */

export interface SpokenReplyProps {
  text: string;
  voice?: string;
  autoPlay?: boolean;
}

export default function SpokenReply({ text, voice, autoPlay }: SpokenReplyProps) {
  const { state, error, speak, stop } = useSpeech();

  useEffect(() => {
    if (autoPlay && text.trim()) void speak(text, voice);
    // Speak once per (text, autoPlay) change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay, text]);

  const playing = state === "playing";
  const loading = state === "loading";

  return (
    <div className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={() => {
          if (playing) {
            stop();
          } else {
            // Living-TV: listen to reply — curious glance.
            emitWernerExperience("highlight");
            void speak(text, voice);
          }
        }}
        disabled={loading}
        aria-label={playing ? "Stop audio reply" : "Listen to reply"}
        className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-1 rounded-md border border-rule dark:border-charcoal-1 text-ink dark:text-bright hover:bg-ice-3 dark:hover:bg-charcoal-1 disabled:opacity-50"
      >
        <span aria-hidden="true">{playing ? "■" : loading ? "…" : "▶"}</span>
        {playing ? "Stop" : loading ? "Loading" : "Listen"}
      </button>
      {state === "error" && error && (
        <span className="text-[11px] font-mono text-emperor" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
