// SPR-05 / M5 + M6 — Playback overlay for an anchored voice note.
//
// Inline overlay near the glyph: play/pause/scrub, 1×/1.5×/2× speed,
// transcript view, region preview (the anchored bbox is highlighted
// in the PDF while the overlay is open). Esc closes; focus returns
// to the PdfViewer.
//
// Audio fetch: the substrate stores voice-note audio as the row's
// raw_text + the original blob at
// /api/voice/anchor/{anchor_id}/audio (the GET sibling of the POST
// in apps/reading/api/voice/anchor.ts). We use a plain <audio>
// element with credentials so Cloudflare Access cookies travel —
// this reuses the existing audio playback library (the browser).
//
// Transcript timing-info caveat (SPR-05 rigor #1)
// ───────────────────────────────────────────────
// The M5 acceptance criterion says: "clickable timestamp seek if
// transcript has timing info". Sprint 13's whisper client
// (acquisition/voice/client.py) returns a flat string text + a
// scalar duration_seconds — it does NOT request the
// verbose_json "segments" or "words" arrays that would give us
// per-word/per-segment offsets. Therefore on the current substrate
// the transcript has no timing info, and the clickable-timestamp
// affordance is a no-op (not rendered). If/when Sprint 13's
// transcriber is upgraded to capture segments, the renderer
// below can iterate over them and render <button onClick=...>
// per timestamp. The decision to NOT add a placeholder no-op
// button is deliberate (per rigor #1): a non-functional control
// is worse than no control.

import { useCallback, useEffect, useRef, useState } from "react";

import { BehaviorEventType, emitBehaviorEvent } from "../../../lib/behaviorEvents";
import type { VoiceNoteAnchor } from "../../../lib/voiceAnchors";

type PlaybackSpeed = 1 | 1.5 | 2;

export interface VoicePlaybackProps {
  anchor: VoiceNoteAnchor;
  /** Viewport-relative anchor point (the clicked glyph's
   *  center). The overlay auto-positions to avoid clipping the
   *  viewport. */
  anchorTop: number;
  anchorLeft: number;
  /** Optional URL override — the production path resolves to
   *  ``/api/voice/anchor/{anchor_id}/audio`` but tests + storybook
   *  inject a static fixture URL. */
  audioUrl?: string;
  /** Optional transcript text. The substrate fetches this from
   *  the voice_note document's raw_text; the parent layer can
   *  pre-load it. */
  transcript?: string | null;
  onClose: () => void;
}

const OVERLAY_WIDTH = 360;
const OVERLAY_HEIGHT_ESTIMATE = 260;
const SPEEDS: PlaybackSpeed[] = [1, 1.5, 2];

export default function VoicePlayback({
  anchor,
  anchorTop,
  anchorLeft,
  audioUrl,
  transcript,
  onClose,
}: VoicePlaybackProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const playEmittedRef = useRef(false);

  const resolvedAudioUrl =
    audioUrl ?? `/api/voice/anchor/${encodeURIComponent(anchor.anchor_id)}/audio`;

  // Esc closes; focus return is the caller's responsibility (it
  // owns the PdfViewer ref).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const togglePlay = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) {
      void el.play();
    } else {
      el.pause();
    }
  }, []);

  const onScrub = useCallback((seconds: number) => {
    const el = audioRef.current;
    if (!el || !Number.isFinite(seconds)) return;
    el.currentTime = Math.max(0, Math.min(seconds, duration || seconds));
  }, [duration]);

  const onSpeedChange = useCallback((s: PlaybackSpeed) => {
    setSpeed(s);
    const el = audioRef.current;
    if (el) el.playbackRate = s;
  }, []);

  const onAudioPlay = useCallback(() => {
    setPlaying(true);
    // M6 — emit voice_note_played ONCE per play, not on resume.
    // We gate via playEmittedRef so a pause+play doesn't re-emit.
    // (The spec: "once per play, not on resume from pause".)
    if (playEmittedRef.current) return;
    playEmittedRef.current = true;
    try {
      emitBehaviorEvent({
        eventType: BehaviorEventType.VOICE_NOTE_PLAYED,
        state: { document_id: anchor.document_id },
        action: {
          voice_note_id: anchor.voice_note_id,
          played_to_completion: null,
          played_fraction: null,
        },
        documentId: anchor.document_id,
      });
    } catch (e) {
      // Best-effort. Don't break playback.
      // eslint-disable-next-line no-console
      console.warn("[voice-playback] emit voice_note_played failed:", e);
    }
  }, [anchor.document_id, anchor.voice_note_id]);

  // Compute overlay position — flip if it would clip viewport.
  const top = (() => {
    const vpHeight = window.innerHeight;
    const wantBelow = anchorTop + 12;
    if (wantBelow + OVERLAY_HEIGHT_ESTIMATE < vpHeight - 16) {
      return wantBelow;
    }
    return Math.max(16, anchorTop - OVERLAY_HEIGHT_ESTIMATE - 12);
  })();
  const left = Math.max(
    16,
    Math.min(
      window.innerWidth - OVERLAY_WIDTH - 16,
      anchorLeft - OVERLAY_WIDTH / 2,
    ),
  );

  return (
    <div
      role="dialog"
      aria-label="Voice note playback"
      style={{
        position: "fixed",
        top,
        left,
        width: OVERLAY_WIDTH,
        zIndex: 50,
      }}
      className="bg-white border-2 border-stone-900 rounded-md shadow-lg p-3 space-y-2"
      data-testid="voice-playback"
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-stone-900">
          Voice note
        </p>
        <button
          type="button"
          onClick={onClose}
          className="text-xs font-mono text-stone-500 hover:text-stone-900"
          aria-label="Close playback"
        >
          ✕ Esc
        </button>
      </div>

      <audio
        ref={audioRef}
        src={resolvedAudioUrl}
        onLoadedMetadata={(e) =>
          setDuration((e.target as HTMLAudioElement).duration || 0)
        }
        onTimeUpdate={(e) =>
          setCurrentTime((e.target as HTMLAudioElement).currentTime)
        }
        onPlay={onAudioPlay}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={togglePlay}
          className="w-9 h-9 rounded-full bg-stone-900 text-white flex items-center justify-center hover:bg-stone-700"
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? "▌▌" : "▶"}
        </button>
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.1}
          value={currentTime}
          onChange={(e) => onScrub(Number(e.target.value))}
          className="flex-1"
          aria-label="Scrub"
        />
        <span className="text-[11px] font-mono text-stone-500 w-14 text-right">
          {fmt(currentTime)} / {fmt(duration)}
        </span>
      </div>

      <div className="flex items-center gap-1">
        <span className="text-[11px] font-mono text-stone-500">speed</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onSpeedChange(s)}
            className={
              "px-2 py-0.5 text-[11px] font-mono rounded " +
              (speed === s
                ? "bg-stone-900 text-white"
                : "bg-stone-100 text-stone-700 hover:bg-stone-200")
            }
          >
            {s}×
          </button>
        ))}
      </div>

      <div className="border-t border-stone-200 pt-2">
        <p className="text-[11px] font-mono text-stone-500 mb-1">
          transcript
        </p>
        <div className="text-xs text-stone-900 max-h-32 overflow-y-auto whitespace-pre-wrap">
          {transcript ?? <span className="text-stone-400">No transcript available.</span>}
        </div>
      </div>
    </div>
  );
}

function fmt(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
