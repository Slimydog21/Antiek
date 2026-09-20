import { WritingNibCursor } from "../WritingNibCursor";
import { registerActivity } from "./registry";
import type { StationActivity } from "./types";

/** Writing-work activity: the pointer becomes a quiet drafting instrument
 * while Werner remains at his station. */
export const writingNibActivity: StationActivity = {
  id: "writing-nib",
  label: "Writing nib",
  ambient: {
    activeClass: null,
    idleClass: null,
  },
  instrument: {
    render: WritingNibCursor,
    reads: ["live", "pointerIdle", "tabHidden"],
  },
  unlock: { kind: "route", policyId: "writing-work" },
};

registerActivity(writingNibActivity);
