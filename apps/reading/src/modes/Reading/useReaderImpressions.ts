import { useCallback, useEffect, useRef } from "react";

import type { AdFillView } from "./AdBorder";
import { recordAdImpressions } from "../../api/books";
import type { ImpressionItem } from "../../api/books";

/**
 * Reader ad-impression flushing (Read SPR-05 → SPR-09).
 *
 * Tracks how long the reader rests on a page (focused dwell) and, when
 * the page changes or the reader leaves, flushes one impression per
 * border slot to the backend. The server applies the attention rule and
 * accrues; this hook's job is honest measurement:
 *
 * - Dwell accumulates only while the tab is focused. `visibilitychange`
 *   pauses/resumes the timer, so a backgrounded tab adds no dwell — the
 *   "attention not while idle" rule, enforced client-side too (the server
 *   re-checks, but we don't even send inflated dwell).
 * - `tab_focused` at flush time is sent so the server can hard-zero
 *   attention for a flush that fired while hidden.
 *
 * Best-effort: a failed flush is swallowed — ad bookkeeping never
 * disrupts reading.
 */

interface PageContext {
  pageIndex: number;
  slots: { slotId: string; fill: AdFillView }[];
}

function nowMs(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

/** Cumulative focused-dwell evidence for the whole reading session, reported
 * out of the hook so a consumer (the source.read emit, SPR-07 M4) can decide a
 * "read" verdict from the SAME focused-dwell clock the ad-impression flush uses
 * — not a second, divergent timer. `pagesSeen` is the count of DISTINCT pages
 * the reader dwelled on this session. */
export interface ReaderDwell {
  totalDwellMs: number;
  pagesSeen: number;
  /** The page whose focused interval was just flushed. */
  pageIndex: number;
}

export function useReaderImpressions(
  documentId: string,
  sessionId: string,
  /** Optional: called on each page-flush with the session's cumulative focused
   * dwell + distinct pages seen. SPR-07 M4 uses this to fire source.read once
   * per session on the dwell threshold — reusing this clock, not adding one. */
  onDwell?: (dwell: ReaderDwell) => void,
) {
  // Accumulated focused dwell for the current page + the wall-clock at
  // which the current focused interval started (null while hidden).
  const dwellMsRef = useRef(0);
  const focusedSinceRef = useRef<number | null>(nowMs());
  const pageRef = useRef<PageContext | null>(null);
  // Session-cumulative dwell + the distinct pages dwelled on — the source.read
  // evidence. Separate from dwellMsRef (which the ad flush zeroes per page); this
  // never resets within a session, so it measures total time-on-book.
  const sessionDwellMsRef = useRef(0);
  const seenPagesRef = useRef<Set<number>>(new Set());
  const onDwellRef = useRef(onDwell);
  onDwellRef.current = onDwell;

  const accumulate = useCallback(() => {
    if (focusedSinceRef.current !== null) {
      const delta = nowMs() - focusedSinceRef.current;
      dwellMsRef.current += delta;
      sessionDwellMsRef.current += delta;
      focusedSinceRef.current = null;
    }
  }, []);

  const resume = useCallback(() => {
    if (focusedSinceRef.current === null) focusedSinceRef.current = nowMs();
  }, []);

  const flush = useCallback(() => {
    accumulate();
    const ctx = pageRef.current;
    const dwell = Math.round(dwellMsRef.current);
    dwellMsRef.current = 0;
    if (!ctx) {
      resume();
      return;
    }
    const tabFocused = typeof document === "undefined" || !document.hidden;
    const items: ImpressionItem[] = ctx.slots.map(({ slotId, fill }) => ({
      slot_id: slotId,
      page_index: ctx.pageIndex,
      fill_kind: fill.kind,
      revenue_usd_cents: fill.kind === "ad" ? 0 : 0, // paid CPM resolution is a later wiring; house is $0
      focused_dwell_ms: dwell,
      tab_focused: tabFocused,
    }));
    if (items.length > 0) {
      void recordAdImpressions(documentId, sessionId, items).catch(() => {
        /* Ad bookkeeping must never disrupt reading. */
      });
    }
    // Report the SESSION-cumulative dwell evidence (SPR-07 M4). The consumer
    // decides the source.read "read" verdict from this; the hook just measures.
    onDwellRef.current?.({
      totalDwellMs: sessionDwellMsRef.current,
      pagesSeen: seenPagesRef.current.size,
      pageIndex: ctx.pageIndex,
    });
    resume();
  }, [accumulate, resume, documentId, sessionId]);

  /** The reader calls this whenever the visible page changes. It flushes
   * the page that was showing, then starts the dwell clock for the new
   * one. */
  const observePage = useCallback(
    (pageIndex: number, slots: { slotId: string; fill: AdFillView }[]) => {
      if (pageRef.current && pageRef.current.pageIndex !== pageIndex) {
        flush();
      }
      seenPagesRef.current.add(pageIndex); // distinct-pages evidence (M4)
      pageRef.current = { pageIndex, slots };
      // (Re)start the dwell clock for the page now showing.
      if (focusedSinceRef.current === null) focusedSinceRef.current = nowMs();
    },
    [flush],
  );

  // Pause/resume the dwell timer with tab visibility, and flush on unload.
  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) accumulate();
      else resume();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flush);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flush);
      flush(); // flush the last page on unmount
    };
  }, [accumulate, resume, flush]);

  return { observePage, flush };
}
