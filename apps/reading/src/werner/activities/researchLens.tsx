import { ResearchLensCursor } from "../ResearchLensCursor";
import { registerActivity } from "./registry";
import type { StationActivity } from "./types";

/** Knowledge-work activity: the cursor becomes an evidence lens while Werner
 * holds his station. No mascot ambient is applied when the pointer rests. */
export const researchLensActivity: StationActivity = {
  id: "research-lens",
  label: "Research lens",
  ambient: {
    activeClass: null,
    idleClass: null,
  },
  instrument: {
    render: ResearchLensCursor,
    reads: ["live", "pointerIdle", "tabHidden"],
  },
  unlock: { kind: "route", policyId: "knowledge-work" },
};

registerActivity(researchLensActivity);
