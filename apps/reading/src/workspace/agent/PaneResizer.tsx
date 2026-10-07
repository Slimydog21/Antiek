/**
 * PaneResizer.tsx — the keyboard-operable separator between the inset's
 * two panes (SPR-07 M5; refs patterns 4/5/6). LAZY (PanelLayout imports it
 * with React.lazy): it reaches companionStore and agentPaneStore.
 *
 *   keyboard   ArrowLeft grows the right pane by STEP, ArrowRight shrinks
 *              (RTL-aware); Home → aria-valuemin, End → aria-valuemax; each
 *              preventDefault + stopPropagation.
 *   pointer    setPointerCapture drag with a live preview; below
 *              COLLAPSE_THRESHOLD the preview shows PANE_MIN; a release
 *              below it closes the active AGENT tab (closeAgentPane) and
 *              restores the pre-drag width, else snaps to PANE_MIN; Escape,
 *              pointercancel, blur and lostpointercapture abort + restore.
 */
import { useRef, useState } from "react";

import { useCompanion } from "../companionStore";
import { closeAgentPane } from "./agentPaneStore";
import { isAgentPaneTab } from "./agentTypes";
import { COLLAPSE_THRESHOLD, PANE_MIN, STEP, usePaneWidthStore } from "./paneWidthStore";

export interface PaneResizerProps {
  /** The right pane's current (effective) width. */
  width: number;
  /** paneWidthMax(containerWidth, leftDockWidth). */
  max: number;
  /** Live width while dragging; null when the drag ends. */
  onPreview: (width: number | null) => void;
}

export function PaneResizer({ width, max, onPreview }: PaneResizerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ startX: number; startWidth: number; preferredBefore: number | null; pointerId: number; rtl: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  const clamp = (w: number) => Math.min(max, Math.max(PANE_MIN, Math.round(w)));
  const setPreferred = (w: number) => usePaneWidthStore.getState().setPreferred(clamp(w));

  const isRtl = () => {
    const el = ref.current;
    return !!el && typeof getComputedStyle === "function" && getComputedStyle(el).direction === "rtl";
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const rtl = isRtl();
    let next: number | null = null;
    if (e.key === "ArrowLeft") next = width + (rtl ? -STEP : STEP);
    else if (e.key === "ArrowRight") next = width + (rtl ? STEP : -STEP);
    else if (e.key === "Home") next = PANE_MIN;
    else if (e.key === "End") next = max;
    else if (e.key === "Escape" && drag.current) {
      e.preventDefault();
      e.stopPropagation();
      abort();
      return;
    }
    if (next === null) return;
    e.preventDefault();
    e.stopPropagation();
    setPreferred(next);
  };

  const endDrag = () => {
    const d = drag.current;
    drag.current = null;
    setDragging(false);
    onPreview(null);
    const el = ref.current;
    if (d && el && typeof el.releasePointerCapture === "function") {
      try { el.releasePointerCapture(d.pointerId); } catch { /* already released */ }
    }
    return d;
  };

  const abort = () => {
    const d = endDrag();
    if (d) usePaneWidthStore.getState().setPreferred(d.preferredBefore);
  };

  const widthAt = (clientX: number) => {
    const d = drag.current!;
    const dx = clientX - d.startX;
    return d.startWidth + (d.rtl ? dx : -dx);
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const el = ref.current;
    if (el && typeof el.setPointerCapture === "function") el.setPointerCapture(e.pointerId);
    drag.current = { startX: e.clientX, startWidth: width, preferredBefore: usePaneWidthStore.getState().preferred, pointerId: e.pointerId, rtl: isRtl() };
    setDragging(true);
    e.preventDefault();
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const raw = widthAt(e.clientX);
    onPreview(raw < COLLAPSE_THRESHOLD ? PANE_MIN : clamp(raw));
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const raw = widthAt(e.clientX);
    const d = endDrag()!;
    if (raw < COLLAPSE_THRESHOLD) {
      const c = useCompanion.getState();
      const activeTab = c.tabs.find((t) => t.id === c.activeTabId) ?? null;
      if (activeTab && isAgentPaneTab(activeTab)) {
        usePaneWidthStore.getState().setPreferred(d.preferredBefore);
        closeAgentPane(activeTab.id, activeTab.title);
      } else {
        usePaneWidthStore.getState().setPreferred(PANE_MIN);
      }
      return;
    }
    setPreferred(raw);
  };

  return (
    <div
      ref={ref}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the agents pane"
      aria-controls="cockpit-right-pane"
      aria-valuenow={width}
      aria-valuemin={PANE_MIN}
      aria-valuemax={max}
      tabIndex={0}
      data-pane-resizer
      data-dragging={dragging ? "" : undefined}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={abort}
      onLostPointerCapture={() => { if (drag.current) abort(); }}
      onBlur={() => { if (drag.current) abort(); }}
      className="w-3 -mx-1.5 shrink-0 self-stretch cursor-col-resize relative z-10 group outline-none"
    >
      <span
        aria-hidden="true"
        className={`absolute inset-y-0 left-1/2 -translate-x-1/2 w-px ${dragging ? "bg-sun" : "bg-transparent group-hover:bg-sun group-focus-visible:bg-sun"}`}
      />
    </div>
  );
}

export default PaneResizer;
