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
import { useEffect, useRef, useState } from "react";

import { subscribeWorkspaceOwnerAdmission, useWorkspaceOwner, type WorkspaceOwnerSession } from "../../lib/accountWorkspaceOwner";

import { useCompanion } from "../companionStore";
import { captureAgentPaneLease, closeAgentPane, isCurrentAgentPaneLease, type AgentPaneLease } from "./agentPaneStore";
import { isAgentPaneTab } from "./agentTypes";
import { COLLAPSE_THRESHOLD, PANE_MIN, STEP, usePaneWidthStore } from "./paneWidthStore";
import { isConfirmedAgentOwner } from "./turnLifecycle";

export interface PaneResizerProps {
  /** The right pane's current (effective) width. */
  width: number;
  /** paneWidthMax(containerWidth, leftDockWidth). */
  max: number;
  /** Live width while dragging; null when the drag ends. */
  onPreview: (width: number | null) => void;
}

interface Drag {
  owner: WorkspaceOwnerSession;
  node: HTMLDivElement;
  operation: number;
  target: AgentPaneLease | null;
  preview: PaneResizerProps["onPreview"];
  startX: number;
  startWidth: number;
  preferredBefore: number | null;
  pointerId: number;
  rtl: boolean;
}

function releaseCapture(d: Drag): void {
  if (typeof d.node.releasePointerCapture === "function") {
    try { d.node.releasePointerCapture(d.pointerId); } catch { /* already released */ }
  }
}

export function PaneResizer({ width, max, onPreview }: PaneResizerProps) {
  const owner = useWorkspaceOwner();
  const ref = useRef<HTMLDivElement>(null);
  const live = useRef(false);
  const operation = useRef(0);
  const drag = useRef<Drag | null>(null);
  const [dragging, setDragging] = useState(false);
  const clamp = (w: number) => Math.min(max, Math.max(PANE_MIN, Math.round(w)));
  const owns = (d: Drag) => live.current && d.node === ref.current && d.operation === operation.current;
  const current = (d?: Drag) => live.current && ref.current !== null && isConfirmedAgentOwner(d?.owner ?? owner)
    && (!d || owns(d));
  const setPreferred = (w: number, captured = owner) => usePaneWidthStore.getState().setPreferred(clamp(w), captured);

  useEffect(() => {
    live.current = true;
    const retire = () => {
      const d = drag.current;
      if (!d || d.owner !== owner) return;
      drag.current = null;
      operation.current++;
      releaseCapture(d);
      setDragging(false);
    };
    const off = subscribeWorkspaceOwnerAdmission(({ session, state }) => {
      if (session !== owner || state === "retiring" || state === "failed" || session.subject === null) retire();
    });
    return () => {
      off();
      const d = drag.current;
      if (d?.owner === owner) {
        drag.current = null;
        operation.current++;
        releaseCapture(d);
        if (isConfirmedAgentOwner(owner)) d.preview(null);
      }
      live.current = false;
    };
  }, [owner]);

  const isRtl = () => {
    const el = ref.current;
    return !!el && typeof getComputedStyle === "function" && getComputedStyle(el).direction === "rtl";
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!current() || e.currentTarget !== ref.current) return;
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

  const endDrag = (d: Drag) => {
    if (drag.current !== d) return false;
    const publish = current(d);
    drag.current = null;
    setDragging(false);
    releaseCapture(d);
    if (!publish || !current(d) || drag.current !== null) return false;
    d.preview(null);
    return current(d) && drag.current === null;
  };

  const abort = (pointerId?: number) => {
    const d = drag.current;
    if (!d || !owns(d) || (pointerId !== undefined && pointerId !== d.pointerId)) return;
    if (endDrag(d)) usePaneWidthStore.getState().setPreferred(d.preferredBefore, d.owner);
  };

  const widthAt = (clientX: number) => {
    const d = drag.current!;
    const dx = clientX - d.startX;
    return d.startWidth + (d.rtl ? dx : -dx);
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || drag.current || !current() || e.currentTarget !== ref.current) return;
    const el = ref.current;
    if (!el) return;
    const c = useCompanion.getState();
    const active = c.tabs.find((t) => t.id === c.activeTabId);
    const d: Drag = { owner, node: el, operation: ++operation.current, target: active && isAgentPaneTab(active) ? captureAgentPaneLease(active.id) : null,
      preview: onPreview, startX: e.clientX, startWidth: width, preferredBefore: usePaneWidthStore.getState().preferred, pointerId: e.pointerId, rtl: isRtl() };
    drag.current = d;
    try { if (typeof el.setPointerCapture === "function") el.setPointerCapture(e.pointerId); }
    catch {
      if (drag.current === d) { drag.current = null; operation.current++; releaseCapture(d); }
      return;
    }
    if (!current(d) || drag.current !== d) {
      if (drag.current === d) { drag.current = null; operation.current++; releaseCapture(d); }
      return;
    }
    setDragging(true);
    e.preventDefault();
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || !current(d) || e.pointerId !== d.pointerId) return;
    const raw = widthAt(e.clientX);
    d.preview(raw < COLLAPSE_THRESHOLD ? PANE_MIN : clamp(raw));
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || !owns(d) || e.pointerId !== d.pointerId) return;
    if (!current(d)) { endDrag(d); return; }
    const raw = widthAt(e.clientX);
    if (!endDrag(d)) return;
    if (raw < COLLAPSE_THRESHOLD) {
      const c = useCompanion.getState();
      const activeTab = c.tabs.find((t) => t.id === c.activeTabId) ?? null;
      if (activeTab && isAgentPaneTab(activeTab)) {
        if (!d.target || d.target.tabId !== activeTab.id || !isCurrentAgentPaneLease(d.target)) return;
        usePaneWidthStore.getState().setPreferred(d.preferredBefore, d.owner);
        if (!current(d) || drag.current !== null || !isCurrentAgentPaneLease(d.target)
            || useCompanion.getState().activeTabId !== activeTab.id) return;
        closeAgentPane(activeTab.id, activeTab.title);
      } else {
        usePaneWidthStore.getState().setPreferred(PANE_MIN, d.owner);
      }
      return;
    }
    setPreferred(raw, d.owner);
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
      onPointerCancel={(e) => abort(e.pointerId)}
      onLostPointerCapture={(e) => abort(e.pointerId)}
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
