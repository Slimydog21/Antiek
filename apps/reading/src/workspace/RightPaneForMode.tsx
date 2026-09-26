/**
 * RightPaneForMode — the mode-aware right pane (C4/C5 contract): the right
 * inset pane (and the conceptual right surface) is the COMPANION in
 * research/reading modes and the OUTLINE in writing mode. One component
 * contract, switched by the route's mothership; the door never sees two
 * panes. Router-guarded like the document strip (PanelLayout's router-free
 * tests get the companion, their previous right pane).
 *
 * Both panes load on first show, not with the entry chunk (it has a hard
 * gzip budget, npm run build:check); each says what it is loading meanwhile.
 */
import { Suspense, lazy } from "react";
import { useInRouterContext, useLocation } from "react-router-dom";

import { mothershipForPath } from "./mothershipForPath";

const CompanionPane = lazy(() => import("./CompanionPane"));
const WriteOutlinePane = lazy(() => import("./WriteOutlinePane"));

function PaneLoading({ what }: { what: string }) {
  return (
    <div role="status" aria-live="polite" className="flex-1 min-h-0 px-3 py-2 text-xs text-ink-mute dark:text-moonlight">
      Loading {what}…
    </div>
  );
}

function Companion() {
  return (
    <Suspense fallback={<PaneLoading what="agents" />}>
      <CompanionPane />
    </Suspense>
  );
}

export default function RightPaneForMode() {
  if (!useInRouterContext()) return <Companion />;
  return <RightPaneForModeInner />;
}

function RightPaneForModeInner() {
  const mothership = mothershipForPath(useLocation().pathname);
  if (mothership === "writing") {
    return (
      <Suspense fallback={<PaneLoading what="outline" />}>
        <WriteOutlinePane />
      </Suspense>
    );
  }
  return <Companion />;
}
