/**
 * useResearchNotifications — sound on REAL research transitions (herdr
 * transfer P1). Mounted once at AppShell. Watches the shared investigation
 * list (same poll cadence as the log) and chimes only on transitions it
 * OBSERVED: completed → done tone, failed → attention tone. Suppressed
 * while the operator is watching that research (route matches /inv/:id
 * and the window has focus) — herdr's suppress-when-watching rule.
 *
 * First load seeds the baseline: pre-existing states never chime.
 */
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { useInvestigationList } from "./useInvestigationList";
import { playResearchAttention, playResearchDone } from "../shared/notifySound";
import type { InvestigationSummary } from "../lib/api";

export function useResearchNotifications(): void {
  const { investigations } = useInvestigationList({ limit: 100 });
  const { pathname } = useLocation();
  // Baseline: status per id as of the previous poll tick.
  const prevRef = useRef<Map<string, InvestigationSummary["status"]>>(
    new Map(),
  );
  const seededRef = useRef(false);

  useEffect(() => {
    if (!seededRef.current) {
      // First tick = baseline, never a chime.
      prevRef.current = new Map(
        investigations.map((s) => [s.investigation_id, s.status]),
      );
      seededRef.current = true;
      return;
    }
    const prev = prevRef.current;
    const watching =
      typeof document !== "undefined" && document.hasFocus();
    for (const s of investigations) {
      const before = prev.get(s.investigation_id);
      if (!before || before === s.status) continue;
      if (s.status === "completed" && before === "in_progress") {
        // Suppressed while the operator is looking at this exact research.
        if (watching && pathname === `/inv/${s.investigation_id}`) continue;
        playResearchDone();
      } else if (s.status === "failed" && before === "in_progress") {
        if (watching && pathname === `/inv/${s.investigation_id}`) continue;
        playResearchAttention();
      }
    }
    prevRef.current = new Map(
      investigations.map((s) => [s.investigation_id, s.status]),
    );
  }, [investigations, pathname]);
}
