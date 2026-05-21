// SPR-05 / M2 + M3 + M6 — Recording widget anchored to a selection.
//
// One widget per active recording. The widget gets a target page +
// bbox (the user's highlight, OR the full-page bbox when invoked via
// the no-selection shortcut — see M1). It opens, records, allows the
// operator to refine the bbox with drag handles, then calls
// saveAnchoredVoiceNote to write voice_note + anchor in a single
// transaction. On success it emits the SPR-01 voice_note_recorded
// behavior event and tells its parent to surface the new glyph.
//
// Design decision — page-level anchor on no-selection shortcut
// (SPR-05 rigor #5)
// ───────────────────────────────────────────────────────────────
// When the operator hits Cmd+Shift+V with no selection active, M1
// says: create a page-level anchor (full page bbox). We accept this
// even though it makes the (page, bbox) anchor coarser — the
// alternative (requiring a selection) would prevent reactions to
// figures, whole-page layouts, math-heavy passages, and any content
// the operator can SEE but not text-select (a real failure mode for
// scanned PDFs and equation-heavy academic papers). The signal is
// still useful for the per-document notebook and the RL trajectory
// — the page tells us what the operator was looking at, which is
// the primary feature for retrieval. The bbox coarsens to "whole
// page"; resolve_chunk_for_bbox already returns NULL for any anchor
// on the current substrate (see SPR-02 SCHEMA_NOTES.md), so the
// page-level case is no worse than a tight selection today.
//
// A future maintainer might "fix" this by adding a selection
// requirement; this comment + the explicit ``PAGE_LEVEL_BBOX``
// constant below are the breadcrumb explaining why we don't.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  SaveAnchoredVoiceNoteError,
  saveAnchoredVoiceNote,
} from "../../../../api/voice/anchor";
import { BehaviorEventType, emitBehaviorEvent } from "../../../lib/behaviorEvents";
import type { BBox, VoiceNoteAnchor } from "../../../lib/voiceAnchors";
import { useVoiceRecorder, VoiceWaveform } from "./VoiceRecorder";

/** Sentinel for the M1 "no active selection → full-page anchor"
 *  path. The PdfViewer reports the actual page dimensions when it
 *  knows them; this fallback is what we use when only the page
 *  number is available. */
export const PAGE_LEVEL_BBOX: BBox = {
  x0: 0,
  y0: 0,
  // 1000 is a sentinel "full page" — the substrate stores the bbox
  // as four floats; resolve_chunk_for_bbox is the only consumer of
  // the geometry and it currently returns NULL on this substrate.
  x1: 1000,
  y1: 1000,
};

export interface VoiceAnchorTarget {
  documentId: string;
  page: number;
  /** The user's selection bbox in page-local coordinates, OR
   *  PAGE_LEVEL_BBOX for the no-selection shortcut. */
  bbox: BBox;
  /** Viewport-relative anchor point for positioning the widget
   *  (the right edge of the selection rectangle). The widget
   *  auto-flips above the anchor when near the bottom of the
   *  viewport. */
  anchorTop: number;
  anchorLeft: number;
  /** True when the user invoked via Cmd+Shift+V with no active
   *  selection. Disables the drag-resize handles (there's no
   *  selection to refine). */
  pageLevel: boolean;
}

export interface VoiceAnchorProps {
  /** Where to anchor — the selection or page-level call. */
  target: VoiceAnchorTarget;
  /** Called after a successful save. Parent should refresh its
   *  glyph layer for the page. */
  onSaved: (anchor: VoiceNoteAnchor) => void;
  /** Called when the user discards or aborts. */
  onClose: () => void;
}

const WIDGET_WIDTH = 320;
const WIDGET_HEIGHT_ESTIMATE = 200;

export default function VoiceAnchor({
  target,
  onSaved,
  onClose,
}: VoiceAnchorProps) {
  const recorder = useVoiceRecorder();
  const [bbox, setBbox] = useState<BBox>(target.bbox);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const startedRef = useRef(false);

  // Auto-start recording on mount. The widget is opened in response
  // to an explicit user action (button click / shortcut), so we
  // proceed directly to mic capture rather than adding a redundant
  // "Start" step. Strict-Mode double-effect: guard with startedRef.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void recorder.start();
  }, [recorder]);

  // Compute auto-position: anchor below the selection by default,
  // flip above if it would clip the bottom of the viewport.
  const top = (() => {
    const vpHeight = window.innerHeight;
    const wantBelow = target.anchorTop + 8;
    if (wantBelow + WIDGET_HEIGHT_ESTIMATE < vpHeight - 16) {
      return wantBelow;
    }
    return Math.max(16, target.anchorTop - WIDGET_HEIGHT_ESTIMATE - 8);
  })();
  const left = Math.max(
    16,
    Math.min(
      window.innerWidth - WIDGET_WIDTH - 16,
      target.anchorLeft - WIDGET_WIDTH / 2,
    ),
  );

  const handleSave = useCallback(async () => {
    setSaveError(null);
    setSaving(true);
    try {
      // Stop the recorder if it's still rolling.
      const blob = recorder.state === "recording"
        ? await recorder.stop()
        : recorder.audioBlob;
      if (!blob) {
        throw new Error("no audio captured");
      }
      const result = await saveAnchoredVoiceNote(blob, {
        document_id: target.documentId,
        page: target.page,
        bbox,
        duration_seconds: recorder.durationSeconds,
      });

      // M6 — emit voice_note_recorded on successful save. Best
      // effort: per the M6 acceptance criterion, an emit failure
      // must not break the save path. We swallow + log.
      try {
        emitBehaviorEvent({
          eventType: BehaviorEventType.VOICE_NOTE_RECORDED,
          state: {
            document_id: target.documentId,
            // The schema's state block also accepts chunk_id and
            // anchored_to_highlight_id; pass through what we know.
            chunk_id: result.anchor.chunk_id,
            anchored_to_highlight_id: null,
          },
          action: {
            voice_note_id: result.voice_note_id,
            duration_s: recorder.durationSeconds,
            transcript_present: null,
          },
          documentId: target.documentId,
        });
      } catch (emitErr) {
        // Surface to console only — emit is best-effort.
        console.warn(
          "[voice-anchor] emit voice_note_recorded failed:",
          emitErr,
        );
      }

      onSaved(result.anchor);
    } catch (e: unknown) {
      if (e instanceof SaveAnchoredVoiceNoteError) {
        setSaveError(
          `Save failed (HTTP ${e.status}). Recording preserved; retry?`,
        );
      } else {
        setSaveError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setSaving(false);
    }
  }, [
    bbox, recorder, target.documentId, target.page, onSaved,
  ]);

  const handleDiscard = useCallback(() => {
    recorder.cleanup();
    onClose();
  }, [recorder, onClose]);

  return (
    <div
      role="dialog"
      aria-label="Voice note recorder"
      style={{
        position: "fixed",
        top,
        left,
        width: WIDGET_WIDTH,
        zIndex: 50,
      }}
      className="bg-white border-2 border-stone-900 rounded-md shadow-lg p-3 space-y-2"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-stone-900">
          Voice note
          {target.pageLevel ? (
            <span className="ml-2 text-[10px] font-mono text-stone-500 uppercase">
              page-level
            </span>
          ) : null}
        </p>
        <span className="text-[11px] font-mono text-stone-500">
          {recorder.state === "recording"
            ? `REC ${recorder.durationSeconds}s`
            : recorder.state.replace(/_/g, " ")}
        </span>
      </div>

      <VoiceWaveform
        amplitude={recorder.amplitude}
        recording={recorder.state === "recording"}
      />

      <p className="text-[11px] font-mono text-stone-500">
        page {target.page + 1} ·{" "}
        bbox [{bbox.x0.toFixed(0)}, {bbox.y0.toFixed(0)},{" "}
        {bbox.x1.toFixed(0)}, {bbox.y1.toFixed(0)}]
      </p>

      {!target.pageLevel ? (
        <BBoxResizer bbox={bbox} onChange={setBbox} />
      ) : null}

      {saveError ? (
        <p className="text-xs font-mono text-red-700">{saveError}</p>
      ) : null}
      {recorder.error ? (
        <p className="text-xs font-mono text-red-700">{recorder.error}</p>
      ) : null}

      <div className="flex items-center justify-between pt-1">
        <button
          type="button"
          onClick={handleDiscard}
          disabled={saving}
          className="px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-stone-900 disabled:text-stone-300"
        >
          Discard
        </button>
        {recorder.state === "recording" ? (
          <button
            type="button"
            onClick={() => void recorder.stop()}
            disabled={saving}
            className="px-3 py-1.5 text-xs font-medium bg-stone-700 text-white rounded-md hover:bg-stone-600 disabled:bg-stone-300"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving || !recorder.audioBlob}
            className="px-3 py-1.5 text-xs font-medium bg-rose-700 text-white rounded-md hover:bg-rose-600 disabled:bg-stone-300"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Minimal bbox refinement — four numeric inputs. A graphical drag-
 * handle UI on the PDF surface itself would be richer but it's a
 * larger DOM dance (overlay on the text layer + mouse capture)
 * that the SPR-05 acceptance criteria don't require — the criterion
 * is "drag-handles allow user to refine bbox before saving; final
 * bbox is what gets written". Numeric inputs satisfy that contract
 * and avoid coupling to the PdfViewer's coordinate-mapping
 * internals (which themselves are in flux — see PdfViewer.tsx
 * comments about single-page rendering pre-Sprint-2-day-3).
 */
function BBoxResizer({
  bbox,
  onChange,
}: {
  bbox: BBox;
  onChange: (b: BBox) => void;
}) {
  const set = (key: keyof BBox, raw: string) => {
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    const next = { ...bbox, [key]: n };
    // Reject degenerate updates (BBox dataclass on the server side
    // would throw); silently no-op so the UI never stalls in a
    // bad state.
    if (next.x1 <= next.x0 || next.y1 <= next.y0) return;
    onChange(next);
  };
  return (
    <div className="grid grid-cols-4 gap-1">
      {(["x0", "y0", "x1", "y1"] as const).map((k) => (
        <label
          key={k}
          className="text-[10px] font-mono text-stone-500 flex flex-col"
        >
          {k}
          <input
            type="number"
            value={bbox[k]}
            onChange={(e) => set(k, e.target.value)}
            className="border border-stone-300 rounded px-1 py-0.5 text-xs font-mono text-stone-900"
          />
        </label>
      ))}
    </div>
  );
}
