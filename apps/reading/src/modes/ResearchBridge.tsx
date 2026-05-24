/**
 * ResearchBridge — mode wrapper mounting the Deep Research Bridge.
 *
 * Matches the one-default-export-per-mode convention used by every
 * other entry in App.tsx. The actual surface (Paste | Gap-finder
 * tabs over the shared substrate) lives in
 * ``./research_bridge/ResearchBridgeHome``; this file is the route
 * adapter only. The home shell builds its own HTTP client, so this
 * wrapper takes no props.
 */

import { ResearchBridgeHome } from "./research_bridge/ResearchBridgeHome";

export default function ResearchBridge() {
  return (
    <div className="p-4 h-full">
      <ResearchBridgeHome />
    </div>
  );
}
