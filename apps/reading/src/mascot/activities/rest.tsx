import { registerActivity } from "./registry";
import type { StationActivity } from "./types";

/**
 * Rest — the calm default station activity (2026-08-13).
 *
 * The ice-fishing activity (bait worm + rod-tip→cursor line) was REMOVED at
 * the operator's directive: "get rid of the fishing rod in the cursor ...
 * stop the brain from following the cursor." The default activity is now
 * REST: the brain stands at its fixed station with no cursor instrument and
 * no ambient gag — blink, breathe, emotes and the directed stroll remain.
 * The registry spine (no-move invariant, registration surface) is unchanged.
 */
export const restActivity: StationActivity = {
  id: "rest",
  label: "Rest",
  ambient: {
    activeClass: null,
    idleClass: null,
  },
  instrument: {
    render: null,
    reads: [],
  },
  unlock: { kind: "default" },
};

// Seed the catalog + mark rest the default. Importing this module (which the
// activities barrel does) is what makes getDefaultActivity() resolve.
registerActivity(restActivity, { default: true });
