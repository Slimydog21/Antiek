/**
 * useFaviconAttention — the favicon as a status surface (herdr transfer P2,
 * strategy 27 follow-up). Composes with the BRAND MARK: the source icon is
 * loaded once, then repainted with a state dot in the corner (emperor =
 * needs attention, aurora = unread) whenever the research attention state
 * changes. With no attention the plain brand mark is restored — the favicon
 * never drifts from brand art.
 */
import { useEffect, useRef } from "react";

import { useInvestigationList } from "./useInvestigationList";
import { isUnseen, researchStateStyle } from "../shared/researchState";
import { lastSeenAt } from "../workspace/seen";
import { accent, surface } from "../design/tokens";

export type DotColor = "blocked" | "unread" | null;

/** Pure attention → dot-color decision, exported for unit tests. */
export function dotColorFor(
  blockedCount: number,
  unreadCount: number,
): DotColor {
  if (blockedCount > 0) return "blocked";
  if (unreadCount > 0) return "unread";
  return null;
}

// Sourced from the token module (never raw hex in a component — the
// token-lint gate enforces this): emperor for blocked, aurora for unread.
const DOT_HEX: Record<Exclude<DotColor, null>, string> = {
  blocked: accent.emperor.day,
  unread: accent.aurora.day,
};

function paintFavicon(sourceUrl: string, dot: DotColor): void {
  if (typeof document === "undefined") return;
  const img = new Image();
  img.onload = () => {
    const size = Math.max(img.width, 16);
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    const g = c.getContext("2d");
    if (!g) return;
    g.drawImage(img, 0, 0, size, size);
    if (dot) {
      g.fillStyle = DOT_HEX[dot];
      g.beginPath();
      g.arc(size - 5, size - 5, 5, 0, Math.PI * 2);
      g.fill();
      // Thin light ring so the dot reads on any favicon color. Sourced from
      // the token module (ice-0 = pure white) — token-lint gate.
      g.strokeStyle = surface.day[0];
      g.lineWidth = 1.5;
      g.stroke();
    }
    let link = document.querySelector<HTMLLinkElement>(
      'link[rel="icon"][data-state-dot]',
    );
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      link.setAttribute("data-state-dot", "");
      document.head.appendChild(link);
    }
    link.href = c.toDataURL("image/png");
  };
  img.src = sourceUrl;
}

export function useFaviconAttention(): void {
  const { investigations } = useInvestigationList({ limit: 200 });
  // The brand favicon (mark-32.png) — resolved once; a missing icon falls
  // back to a plain dot-on-transparent so the status still reads.
  const sourceRef = useRef<string | null>(null);

  useEffect(() => {
    if (!sourceRef.current) {
      const existing =
        document.querySelector<HTMLLinkElement>('link[rel="icon"]');
      sourceRef.current =
        existing?.href ??
        (typeof location !== "undefined" ? `${location.origin}/mark-32.png` : null);
    }
    const blocked = investigations.filter(
      (s) => researchStateStyle(s.status).state === "blocked",
    ).length;
    const unread = investigations.filter(
      (s) =>
        s.status === "completed" &&
        isUnseen(s, lastSeenAt(s.investigation_id)),
    ).length;
    if (sourceRef.current) {
      paintFavicon(sourceRef.current, dotColorFor(blocked, unread));
    }
  }, [investigations]);
}
