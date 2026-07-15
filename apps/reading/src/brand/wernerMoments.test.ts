import { describe, expect, it } from "vitest";

import {
  WERNER_MOMENTS,
  fallbackBeat,
  momentForTransition,
  type WernerMoment,
} from "./wernerMoments";
import type { SceneMood } from "../scene/mood";

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };
const DUSK: SceneMood = { dayPart: "dusk", weather: "snow" };
const DAWN: SceneMood = { dayPart: "dawn", weather: "snow" };
const CLEAR_DAY: SceneMood = { dayPart: "day", weather: "clear" };

describe("wernerMoments", () => {
  it("declares a no-focus interruption budget and a hard frequency cap for every moment", () => {
    for (const moment of WERNER_MOMENTS) {
      expect(moment.interruptionBudget).toBe("none");
      expect(moment.frequencyCap.max).toBe(1);
      expect(["per-transition", "per-scene-state"]).toContain(moment.frequencyCap.window);
    }
  });

  it("fires nightfall only when the scene crosses into night", () => {
    const moment = momentForTransition(DAY, NIGHT) as WernerMoment;
    expect(moment.id).toBe("nightfall");
    expect(moment.pose).toBe("thinking");
    expect(moment.settlesTo).toBe("idle");
    expect(momentForTransition(NIGHT, NIGHT)).toBeNull();
    expect(momentForTransition(null, NIGHT)).toBeNull();
  });

  it("fires daybreak only for exact night → dawn (not night → day)", () => {
    // Night → dawn: the civil-time crossing into the dawn window.
    const nightToDawn = momentForTransition(NIGHT, DAWN) as WernerMoment;
    expect(nightToDawn.id).toBe("daybreak");
    expect(nightToDawn.pose).toBe("celebrate");
    expect(nightToDawn.settlesTo).toBe("idle");
    // Night → day: the dawn window was skipped, so no daybreak.
    expect(momentForTransition(NIGHT, DAY)).toBeNull();
    // Dawn → day: not a night→dawn crossing, so null.
    expect(momentForTransition(DAWN, DAY)).toBeNull();
    // Initial dawn (null prev): null.
    expect(momentForTransition(null, DAWN)).toBeNull();
  });

  it("fires dusk-settle on arrival into dusk and otherwise stays quiet", () => {
    const moment = momentForTransition(DAY, DUSK) as WernerMoment;
    expect(moment.id).toBe("dusk-settle");
    expect(moment.pose).toBe("thinking");
    expect(moment.settlesTo).toBe("thinking");
    // Night → day (dawn skipped): no daybreak.
    expect(momentForTransition(NIGHT, DAY)).toBeNull();
    // Weather-only change: no moment.
    expect(momentForTransition(DAY, CLEAR_DAY)).toBeNull();
  });

  it("is deterministic for repeated transition checks", () => {
    expect(momentForTransition(DAY, NIGHT)).toEqual(
      momentForTransition({ ...DAY }, { ...NIGHT }),
    );
    expect(momentForTransition(NIGHT, DAY)).toEqual(
      momentForTransition({ ...NIGHT }, { ...DAY }),
    );
  });

  it("fallback companionship keeps the resting cue and does not dramatize missing live art", () => {
    const beat = fallbackBeat(NIGHT);
    expect(beat.id).toBe("fallback-companion");
    expect(beat.cue.artPresence).toBe("fallback");
    expect(beat.moment.pose).toBe(beat.cue.mood);
    expect(beat.moment.settlesTo).toBe(beat.cue.mood);
    expect(beat.moment.frequencyCap.window).toBe("per-scene-state");
    expect(beat.copy).toBe("No live art here; Werner stays with the procedural scene.");
  });
});
