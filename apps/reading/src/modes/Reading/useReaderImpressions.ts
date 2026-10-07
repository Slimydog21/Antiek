import { useCallback, useEffect, useMemo } from "react";

import type { AdFillView } from "./AdBorder";
import { recordAdImpressions } from "../../api/books";
import type { ImpressionItem } from "../../api/books";
import {
  beforeWorkspaceOwnerChange,
  awaitWorkspaceOwnerSession,
  isWorkspaceOwnerSession,
  subscribeWorkspaceOwnerAdmission,
  workspaceOwnerAdmission,
  useWorkspaceOwner,
  type WorkspaceOwnerSession,
} from "../../lib/accountWorkspaceOwner";

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
}

interface DwellSession {
  readonly owner: WorkspaceOwnerSession;
  readonly controller: AbortController;
  active: boolean;
  dwellMs: number;
  focusedSince: number | null;
  page: PageContext | null;
  totalDwellMs: number;
  pages: Set<number>;
  onDwell: ((dwell: ReaderDwell) => void) | undefined;
}

function isCurrent(measurement: DwellSession): boolean {
  return measurement.active && measurement.owner.subject !== null
    && isWorkspaceOwnerSession(measurement.owner);
}

export function useReaderImpressions(
  documentId: string,
  sessionId: string,
  /** Optional: called on each page-flush with the session's cumulative focused
   * dwell + distinct pages seen. SPR-07 M4 uses this to fire source.read once
   * per session on the dwell threshold — reusing this clock, not adding one. */
  onDwell?: (dwell: ReaderDwell) => void,
) {
  const owner = useWorkspaceOwner();
  // A same-owner document/session change flushes its previous measurement.
  // Account retirement discards it before any cleanup can use a new cookie.
  const measurement = useMemo<DwellSession>(() => ({
    owner,
    controller: new AbortController(),
    active: true,
    dwellMs: 0,
    focusedSince: null,
    page: null,
    totalDwellMs: 0,
    pages: new Set(),
    onDwell: undefined,
  }), [documentId, sessionId, owner]);

  useEffect(() => {
    measurement.onDwell = onDwell;
  }, [measurement, onDwell]);

  const accumulate = useCallback(() => {
    if (measurement.focusedSince !== null) {
      const delta = nowMs() - measurement.focusedSince;
      measurement.dwellMs += delta;
      measurement.totalDwellMs += delta;
      measurement.focusedSince = null;
    }
  }, [measurement]);

  const resume = useCallback(() => {
    if (isCurrent(measurement) && measurement.page && measurement.focusedSince === null
      && (typeof document === "undefined" || !document.hidden)) {
      measurement.focusedSince = nowMs();
    }
  }, [measurement]);

  const flush = useCallback(() => {
    if (!isCurrent(measurement) || !measurement.page) return;
    accumulate();
    const ctx = measurement.page;
    const dwell = Math.round(measurement.dwellMs);
    measurement.dwellMs = 0;
    const tabFocused = typeof document === "undefined" || !document.hidden;
    const items: ImpressionItem[] = ctx.slots.map(({ slotId, fill }) => ({
      slot_id: slotId,
      page_index: ctx.pageIndex,
      fill_kind: fill.kind,
      revenue_usd_cents: fill.kind === "ad" ? 0 : 0, // paid CPM resolution is a later wiring; house is $0
      focused_dwell_ms: dwell,
      tab_focused: tabFocused,
    }));
    const evidence = { totalDwellMs: measurement.totalDwellMs, pagesSeen: measurement.pages.size };
    const callback = measurement.onDwell;
    // A flush owns its captured sample, including a legitimate same-owner
    // leave. Retirement aborts it; a ready observer alone cannot release it.
    void (async () => {
      do {
        if (!await awaitWorkspaceOwnerSession(measurement.owner, measurement.controller.signal)) return;
      } while (!isWorkspaceOwnerSession(measurement.owner));
      if (measurement.controller.signal.aborted) return;
      if (items.length > 0) {
        void recordAdImpressions(documentId, sessionId, items).catch(() => {
          /* best-effort — never disrupt reading */
        });
      }
      if (isWorkspaceOwnerSession(measurement.owner) && !measurement.controller.signal.aborted) callback?.(evidence);
    })();
    resume();
  }, [accumulate, resume, documentId, sessionId, measurement]);

  /** The reader calls this whenever the visible page changes. It flushes
   * the page that was showing, then starts the dwell clock for the new
   * one. */
  const observePage = useCallback(
    (pageIndex: number, slots: { slotId: string; fill: AdFillView }[]) => {
      const admission = workspaceOwnerAdmission();
      if (!measurement.active || admission.session !== measurement.owner
        || (admission.state !== "ready" && admission.state !== "suspended")) return;
      if (measurement.page && measurement.page.pageIndex !== pageIndex) {
        if (isCurrent(measurement)) flush();
        else measurement.dwellMs = 0;
      }
      measurement.pages.add(pageIndex);
      measurement.page = { pageIndex, slots };
      // (Re)start the dwell clock for the page now showing.
      resume();
    },
    [flush, resume, measurement],
  );

  // Pause/resume the dwell timer with tab visibility, and flush on unload.
  useEffect(() => {
    measurement.active = true;
    resume();
    const onAdmission = (admission: ReturnType<typeof workspaceOwnerAdmission>) => {
      if (admission.session !== measurement.owner || admission.state === "retiring" || admission.state === "failed") {
        accumulate();
        measurement.active = false;
        measurement.controller.abort();
      } else if (admission.state === "suspended") {
        accumulate();
      } else {
        resume();
      }
    };
    const unsubscribeAdmission = subscribeWorkspaceOwnerAdmission(onAdmission);
    onAdmission(workspaceOwnerAdmission());
    const unsubscribeRetirement = beforeWorkspaceOwnerChange(() => {
      measurement.active = false;
      measurement.focusedSince = null;
      measurement.controller.abort();
    });
    const onVisibility = () => {
      if (document.hidden) accumulate();
      else resume();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flush);
    return () => {
      unsubscribeRetirement();
      unsubscribeAdmission();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flush);
      try {
        flush();
      } finally {
        measurement.active = false;
        measurement.focusedSince = null;
      }
    };
  }, [accumulate, resume, flush, measurement]);

  return { observePage, flush };
}
