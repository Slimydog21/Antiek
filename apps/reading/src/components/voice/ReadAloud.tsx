/**
 * ReadAloud — the shared, host-agnostic read-aloud control (SPR-14 M2 + M3-out).
 *
 * A play / pause / stop control backed by `api/tts.ts`. It is deliberately NOT
 * Reading-private: any surface (the float-menu in SPR-04, the voice prompt in
 * SPR-05, talk-to-book + audiobook in SPR-08, voice-to-draft in SPR-09, the
 * async interview in SPR-10) mounts THIS component to read a model response
 * aloud. It owns the audio element + the play/pause/stop state machine; it does
 * not own any surface chrome.
 *
 * §9 provenance — narration is MODEL-GENERATED. The control reads text the model
 * produced; it persists nothing, creates no user node, and surfaces the
 * `TTS_OUT_SOURCE_KIND` ("ai") label so a surface that shows provenance never
 * conflates a read-aloud with user content.
 *
 * §9.0 — a withheld region is never narrated. Pass `chunkId`; the control runs
 * the §9.0 guard via `narrate` before any text leaves the client. A withheld
 * source surfaces an honest "withheld from reading aloud" state, and the TTS
 * service is never called.
 *
 * §5 voice — the labels + the withheld/unavailable copy are crafted prose, not
 * slop.
 *
 * jsdom note: HTMLMediaElement.play/pause are unimplemented in jsdom; the tests
 * stub them. In a real browser `new Audio(url)` + `.play()` is the playback path
 * (mirrors hooks/useSpeech.ts).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { narrate, TtsError, TTS_OUT_SOURCE_KIND } from "../../api/tts";
import { emitWernerExperience } from "../../werner/reactionBus";

export type ReadAloudState =
  | "idle"
  | "loading"
  | "playing"
  | "paused"
  | "withheld" // §9.0 — refused, never narrated
  | "error";

export interface ReadAloudProps {
  /** The model-generated text to narrate. Empty/whitespace is a quiet no-op. */
  text: string;
  /** §9.0 — the source chunk; when withheld the control refuses to narrate. */
  chunkId?: string;
  /** Length/time box: scope the narration to ~`minutes` of speech. */
  minutes?: number;
  /** Voice id passed through to the service. */
  voice?: string;
  /** Optional label override; defaults to crafted prose per state. */
  label?: string;
  /** Test seam: build an audio element from the synthesized blob. Defaults to
   *  `new Audio(URL.createObjectURL(blob))`. Tests inject a fake so jsdom's
   *  unimplemented HTMLMediaElement.play does not throw. */
  makeAudio?: (blob: Blob) => HTMLAudioElement;
}

function defaultMakeAudio(blob: Blob): HTMLAudioElement {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  // Stash the url so cleanup can revoke it.
  (audio as HTMLAudioElement & { _objectUrl?: string })._objectUrl = url;
  return audio;
}

export function ReadAloud({
  text,
  chunkId,
  minutes,
  voice,
  label,
  makeAudio = defaultMakeAudio,
}: ReadAloudProps) {
  const [state, setState] = useState<ReadAloudState>("idle");
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const cleanup = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      const url = (audio as HTMLAudioElement & { _objectUrl?: string })._objectUrl;
      if (url) URL.revokeObjectURL(url);
      audioRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    cleanup();
    setState("idle");
    setError(null);
  }, [cleanup]);

  const pause = useCallback(() => {
    if (audioRef.current && state === "playing") {
      audioRef.current.pause();
      setState("paused");
    }
  }, [state]);

  const play = useCallback(async () => {
    // Resume a paused narration without re-synthesizing.
    if (state === "paused" && audioRef.current) {
      await audioRef.current.play();
      setState("playing");
      return;
    }
    // Empty text is a quiet no-op, never a crash (rigor #3 silent/empty).
    if (!text.trim()) return;

    cleanup();
    setState("loading");
    setError(null);
    try {
      // narrate enforces §9.0 (withheld → throws) + length bound + scoping, then
      // synthesizes. The audio is model-generated; no user node is created.
      const result = await narrate(text, { chunkId, minutes, voice });
      const audio = makeAudio(result.audio);
      audioRef.current = audio;
      audio.onended = () => setState("idle");
      audio.onerror = () => {
        setError("Playback failed.");
        setState("error");
      };
      await audio.play();
      setState("playing");
    } catch (e: unknown) {
      if (e instanceof TtsError && e.kind === "withheld") {
        // §9.0 — never narrated. Honest, distinct state (not a generic error).
        setState("withheld");
        setError(e.message);
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }, [state, text, chunkId, minutes, voice, makeAudio, cleanup]);

  // Stop + revoke any object URL on unmount.
  useEffect(() => cleanup, [cleanup]);

  const primaryLabel =
    label ??
    (state === "playing"
      ? "Pause"
      : state === "paused"
        ? "Resume"
        : state === "loading"
          ? "Preparing…"
          : "Read aloud");

  return (
    <div
      className="read-aloud"
      data-state={state}
      // §9 — the provenance of a read-aloud is always model-generated. A surface
      // that reads this attribute must never treat narration as user content.
      data-source-kind={TTS_OUT_SOURCE_KIND}
    >
      {state === "withheld" ? (
        <p className="read-aloud__withheld" role="status">
          {error ?? "This source is withheld and can’t be read aloud."}
        </p>
      ) : (
        <>
          <button
            type="button"
            className="read-aloud__play"
            disabled={state === "loading"}
            aria-label={primaryLabel}
            onClick={() => {
              if (state === "playing") {
                pause();
              } else {
                // play() handles its own errors (incl. the §9.0 withheld
                // refusal) and always resolves; the trailing .catch is a
                // belt-and-braces guard so a click handler never leaks a
                // floating rejection.
                void play().catch(() => undefined);
              }
            }}
          >
            {primaryLabel}
          </button>
          {(state === "playing" || state === "paused") && (
            <button
              type="button"
              className="read-aloud__stop"
              aria-label="Stop"
              onClick={stop}
            >
              Stop
            </button>
          )}
          {state === "error" && error && (
            <p className="read-aloud__error" role="alert">
              {error}
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default ReadAloud;
