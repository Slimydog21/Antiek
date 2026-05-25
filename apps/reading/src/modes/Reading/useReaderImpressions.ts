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

export function useReaderImpressions(documentId: string, sessionId: string) {
  // Accumulated focused dwell for the current page + the wall-clock at
  // which the current focused interval started (null while hidden).
  const dwellMsRef = useRef(0);
  const focusedSinceRef = useRef<number | null>(nowMs());
  const pageRef = useRef<PageContext | null>(null);

  const accumulate = useCallback(() => {
    if (focusedSinceRef.current !== null) {
      dwellMsRef.current += nowMs() - focusedSinceRef.current;
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
    if (!ctx || ctx.slots.length === 0) {
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
    void recordAdImpressions(documentId, sessionId, items).catch(() => {
      /* best-effort — never disrupt reading */
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
