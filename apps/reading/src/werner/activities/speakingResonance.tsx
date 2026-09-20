import { SpeakingResonanceCursor } from "../SpeakingResonanceCursor";
import { registerActivity } from "./registry";
import type { StationActivity } from "./types";

/** Speaking-work activity: the pointer becomes a listening instrument while
 * Werner remains at his station. */
export const speakingResonanceActivity: StationActivity = {
  id: "speaking-resonance",
  label: "Speaking resonance",
  ambient: {
    activeClass: null,
    idleClass: null,
  },
  instrument: {
    render: SpeakingResonanceCursor,
    reads: ["live", "pointerIdle", "tabHidden"],
  },
  unlock: { kind: "route", policyId: "speaking-work" },
};

registerActivity(speakingResonanceActivity);
