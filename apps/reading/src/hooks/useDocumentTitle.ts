/**
 * useDocumentTitle — the OS window list as a status surface (herdr transfer
 * P1, strategy 27). Mounted once in AppShell (main SPA only): popout windows
 * own their own titles in PanelWindowApp and are never clobbered.
 *
 * Rules:
 *   /inv/:id open   → "<question> — <state word> — Antiek"
 *   blocked exist   → "N need attention — Antiek"
 *   unseen exist    → "N unread — Antiek"
 *   otherwise       → "Antiek"
 *
 * (The favicon state-dot variant is a follow-up: it must compose with the
 * brand mark instead of replacing it.)
 */
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { useInvestigationList } from "./useInvestigationList";
import type { InvestigationSummary } from "../lib/api";
import { isUnseen, researchStateLabel, researchStateStyle } from "../shared/researchState";
import { lastSeenAt } from "../workspace/seen";

/** Pure title computation — extracted for unit tests. `seen` is the
 *  lastSeenAt map so the pure function never touches storage. */
export function computeDocumentTitle(
  investigations: InvestigationSummary[],
  pathname: string,
  seen: (id: string) => string | null,
): string {
  const m = pathname.match(/^\/inv\/([^/]+)/);
  if (m) {
    const id = decodeURIComponent(m[1]);
    const active = investigations.find((s) => s.investigation_id === id);
    if (active) {
      const state = researchStateStyle(active.status).state;
      return `${active.question ?? "Research"} — ${researchStateLabel(state)} — Antiek`;
    }
    return "Antiek";
  }
  const blocked = investigations.filter(
    (s) => researchStateStyle(s.status).state === "blocked",
  ).length;
  const unseen = investigations.filter(
    (s) => s.status === "completed" && isUnseen(s, seen(s.investigation_id)),
  ).length;
  if (blocked > 0) return `${blocked} need attention — Antiek`;
  if (unseen > 0) return `${unseen} unread — Antiek`;
  return "Antiek";
}

export function useDocumentTitle(): void {
  const { investigations } = useInvestigationList({ limit: 200 });
  const { pathname } = useLocation();

  useEffect(() => {
    document.title = computeDocumentTitle(investigations, pathname, lastSeenAt);
  }, [investigations, pathname]);
}
