/**
 * RightPaneForMode — the mode-aware right pane (C4/C5 contract): the right
 * inset pane (and the conceptual right surface) is the COMPANION in
 * research/reading modes and the OUTLINE in writing mode. One component
 * contract, switched by the route's mothership; the door never sees two
 * panes. Router-guarded like the document strip (PanelLayout's router-free
 * tests get the companion, their previous right pane).
 */
import { useInRouterContext, useLocation } from "react-router-dom";

import CompanionPane from "./CompanionPane";
import WriteOutlinePane from "./WriteOutlinePane";
import { mothershipForPath } from "./documentSpace";

export default function RightPaneForMode() {
  if (!useInRouterContext()) return <CompanionPane />;
  return <RightPaneForModeInner />;
}

function RightPaneForModeInner() {
  const mothership = mothershipForPath(useLocation().pathname);
  if (mothership === "writing") return <WriteOutlinePane />;
  return <CompanionPane />;
}
