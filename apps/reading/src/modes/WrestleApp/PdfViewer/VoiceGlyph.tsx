// SPR-05 / M4 — Single gutter glyph for an anchored voice note.
//
// Renders one audio-glyph in the page gutter at the bbox's vertical
// center. Hover surfaces a truncated transcript snippet; click
// opens the playback overlay (the parent layer orchestrates which
// overlay is open).

import { useState } from "react";

import type { VoiceNoteAnchor } from "../../../lib/voiceAnchors";

const TRANSCRIPT_HOVER_MAX_CHARS = 80;

export interface VoiceGlyphProps {
  anchor: VoiceNoteAnchor;
  /** Vertical-center position of the bbox in DOM coordinates,
   *  RELATIVE TO THE PAGE CONTAINER (not the viewport). The
   *  glyph layer is positioned absolutely inside the page
   *  container, so glyphs auto-track scroll + zoom because
   *  their parent does. */
  top: number;
  /** Horizontal offset within the gutter. Multiple glyphs on the
   *  same page can collide vertically; the layer stacks them
   *  horizontally by passing different ``left`` values. */
  left: number;
  /** Optional transcript snippet for the hover tooltip. Loaded
   *  lazily by the parent layer. */
  transcriptSnippet?: string | null;
  onOpenPlayback: (anchor: VoiceNoteAnchor) => void;
}

export default function VoiceGlyph({
  anchor,
  top,
  left,
  transcriptSnippet,
  onOpenPlayback,
}: VoiceGlyphProps) {
  const [hovered, setHovered] = useState(false);
  const snippet = (() => {
    if (!transcriptSnippet) return null;
    if (transcriptSnippet.length <= TRANSCRIPT_HOVER_MAX_CHARS) {
      return transcriptSnippet;
    }
    return transcriptSnippet.slice(0, TRANSCRIPT_HOVER_MAX_CHARS) + "…";
  })();

  return (
    <div
      data-testid={`voice-glyph-${anchor.anchor_id}`}
      data-anchor-id={anchor.anchor_id}
      style={{
        position: "absolute",
        top,
        left,
        transform: "translate(-50%, -50%)",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        onClick={() => onOpenPlayback(anchor)}
        aria-label={`Voice note ${anchor.anchor_id}`}
        className="w-6 h-6 rounded-full bg-amber-400 border-2 border-stone-900 shadow flex items-center justify-center hover:bg-amber-300 focus:outline-none focus:ring-2 focus:ring-stone-900"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          aria-hidden="true"
        >
          <rect x="5" y="2" width="2" height="6" rx="1" fill="#151515" />
          <path
            d="M3 6 a3 3 0 0 0 6 0"
            stroke="#151515"
            strokeWidth="1.2"
            fill="none"
          />
          <line
            x1="6"
            y1="9"
            x2="6"
            y2="11"
            stroke="#151515"
            strokeWidth="1.2"
          />
        </svg>
      </button>
      {hovered && snippet ? (
        <div
          role="tooltip"
          style={{
            position: "absolute",
            top: -32,
            left: -8,
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}
          className="bg-stone-900 text-white text-[11px] font-mono px-2 py-1 rounded shadow max-w-xs truncate"
        >
          {snippet}
        </div>
      ) : null}
    </div>
  );
}
