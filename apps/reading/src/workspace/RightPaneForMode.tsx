/**
 * RightPaneForMode — the mode-aware right pane (C4/C5 contract): the right
 * inset pane (and the conceptual right surface) is the COMPANION in
 * research/reading modes and the OUTLINE in writing mode. One component
 * contract, switched by the route's mothership; the door never sees two
 * panes. Router-guarded like the document strip (PanelLayout's router-free
 * tests get the companion, their previous right pane).
 *
 * Both panes load on first show, not with the entry chunk (it has a hard
 * gzip budget, npm run build:check); meanwhile each shows the shared
 * LoadingState, naming what is opening.
 */
import { Suspense, lazy } from "react";
import { useInRouterContext, useLocation } from "react-router-dom";

import { LoadingState } from "../components/states";
import { mothershipForPath } from "./mothershipForPath";

const CompanionPane = lazy(() => import("./CompanionPane"));
const WriteOutlinePane = lazy(() => import("./WriteOutlinePane"));

/** The shared LoadingState, naming what is opening, while a pane's chunk
 *  loads. */
function PaneLoading({ what }: { what: string }) {
  return (
    <div className="flex-1 min-h-0 px-3 py-2">
      <LoadingState variant="inline" shape="list" rows={3} label={`Opening ${what}`} />
    </div>
  );
}

function Companion() {
  return (
    <Suspense fallback={<PaneLoading what="your agents" />}>
      <CompanionPane />
    </Suspense>
  );
}

export default function RightPaneForMode() {
  if (!useInRouterContext()) return <Companion />;
  return <RightPaneForModeInner />;
}

function RightPaneForModeInner() {
  const { pathname, search } = useLocation();
  const mothership = mothershipForPath(pathname, search);
  if (mothership === "writing") {
    return (
      <Suspense fallback={<PaneLoading what="the outline" />}>
        <WriteOutlinePane />
      </Suspense>
    );
  }
  return <Companion />;
}
