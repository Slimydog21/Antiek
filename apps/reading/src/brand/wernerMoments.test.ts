/**
 * wernerMoments.test.ts — the delight moments fire on their EXACT trigger
 * transition, deterministically, and are fully designed under reduced motion
 * (ALC SPR-07 M2).
 *
 * Each moment has a test driving its precise (prev → next) transition and
 * asserting the exact beat (rigor #3 — a delight without a trigger test is an
 * untested path wearing a bow). The suite also proves the NEGATIVES: a first
 * resolve is not a beat, an unchanged scene is not a beat, a phase-drift that
 * keeps the dayPart is not a beat (so a beat can never fire per-frame), and the
 * cut "weather-clears" no-op produces nothing.
 */
import { describe, expect, it } from "vitest";

import {
  momentForTransition,
  fallbackBeat,
  type WernerMoment,
} from "./wernerMoments";
import { sceneDurationMs } from "../design/motion/sceneMotion";
import { durationMs } from "../design/motion";
import type { SceneMood } from "../scene/mood";

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };
const DUSK: SceneMood = { dayPart: "dusk", weather: "snow" };
const DAWN: SceneMood = { dayPart: "dawn", weather: "snow" };
const DAY_CLEAR: SceneMood = { dayPart: "day", weather: "clear" };

describe("wernerMoments — deterministic delight at scene transitions (M2)", () => {
  it("MOMENT nightfall: day → night fires the nightfall beat (the sky's biggest change)", () => {
    const m = momentForTransition(DAY, NIGHT) as WernerMoment;
    expect(m).not.toBeNull();
    expect(m.id).toBe("nightfall");
    expect(m.pose).toBe("thinking"); // a contemplative beat as the dark arrives
    expect(m.settlesTo).toBe("idle"); // settles into the night resting cue
    // Duration is a sceneMotion token (no raw literal) — moves WITH the crossfade.
    expect(m.durationMs).toBe(sceneDurationMs.crossfade);
    // Fully designed under reduced motion: collapse to the settled night pose.
    expect(m.reducedPose).toBe("idle");
  });

  it("MOMENT daybreak: night → day fires the daybreak lift, capped at the signature-beat ceiling", () => {
    const m = momentForTransition(NIGHT, DAY) as WernerMoment;
    expect(m).not.toBeNull();
    expect(m.id).toBe("daybreak");
    expect(m.pose).toBe("celebrate"); // a single quiet lift as the light returns
    expect(m.settlesTo).toBe("idle");
    // Sourced from the 800ms slow ceiling (the celebrate one-shot length).
    expect(m.durationMs).toBe(durationMs.slow);
    expect(m.reducedPose).toBe("idle"); // reduced motion: settle straight to day idle
  });

  it("MOMENT dusk-settle: → dusk eases into the watching tilt (beat == resting pose, arrival not performance)", () => {
    const m = momentForTransition(DAY, DUSK) as WernerMoment;
    expect(m).not.toBeNull();
    expect(m.id).toBe("dusk-settle");
    expect(m.pose).toBe("thinking");
    expect(m.settlesTo).toBe("thinking"); // dusk's resting cue IS thinking
    expect(m.durationMs).toBe(sceneDurationMs.light);
    expect(m.reducedPose).toBe("thinking");
  });

  it("MOMENT fallback-unbothered: missing art ⇒ Werner holds his calm resting pose (procedural is normal)", () => {
    const beatNight = fallbackBeat(NIGHT);
    expect(beatNight.id).toBe("fallback-unbothered");
    // The cue is EXACTLY the resting cue Werner shows when art IS present —
    // unbothered, never a "degraded" pose.
    expect(beatNight.cue.mood).toBe("idle");
    expect(beatNight.cue.sceneKey).toBe("night|snow");
    const beatDay = fallbackBeat(DAY);
    expect(beatDay.cue.mood).toBe("idle");
    // No flourish to collapse: the calm IS the design (nothing to animate, so
    // the reduced-motion state is identical — proven by it being a plain cue).
    expect(beatDay.reason.toLowerCase()).toContain("normal");
    expect(beatDay.reason.toLowerCase()).not.toContain("degraded fallback");
  });

  // ── NEGATIVES: silence is the default; beats are rare and never per-frame. ──

  it("NO beat on first resolve (prev = null): Werner just appears in his resting cue", () => {
    expect(momentForTransition(null, DAY)).toBeNull();
    expect(momentForTransition(null, NIGHT)).toBeNull();
  });

  it("NO beat when the scene is unchanged (same dayPart + weather)", () => {
    expect(momentForTransition(DAY, { ...DAY })).toBeNull();
    expect(momentForTransition(NIGHT, { ...NIGHT })).toBeNull();
  });

  it("NO beat on a phase-drift that keeps the dayPart (a beat can never fire per-frame)", () => {
    // Same dayPart, same weather across a drift tick ⇒ null, every time.
    for (let i = 0; i < 10; i++) {
      expect(momentForTransition(DAY, { ...DAY })).toBeNull();
    }
  });

  it("NO beat for the CUT weather-clears transition (snow ⇄ clear, same dayPart) — the no-op is gone", () => {
    expect(momentForTransition(DAY, DAY_CLEAR)).toBeNull();
    expect(momentForTransition(DAY_CLEAR, DAY)).toBeNull();
  });

  it("NO special beat for a dawn arrival (settles quietly; no dawn pose to perform)", () => {
    expect(momentForTransition(NIGHT, DAWN)).toBeNull();
  });

  // ── DETERMINISM: same transition ⇒ byte-identical moment, every time. ──

  it("DETERMINISTIC: the same transition yields a byte-identical moment (no RNG, no clock)", () => {
    const a = JSON.stringify(momentForTransition(DAY, NIGHT));
    const b = JSON.stringify(momentForTransition({ ...DAY }, { ...NIGHT }));
    expect(b).toBe(a);
    const c = JSON.stringify(momentForTransition(NIGHT, DAY));
    const d = JSON.stringify(momentForTransition({ ...NIGHT }, { ...DAY }));
    expect(d).toBe(c);
  });

  it("DETERMINISTIC: replaying a transition sequence gives the same moment stream", () => {
    const seq: SceneMood[] = [DAY, NIGHT, DAY, DUSK, NIGHT, DAY];
    const run = () => {
      const out: (string | null)[] = [];
      let prev: SceneMood | null = null;
      for (const next of seq) {
        const m = momentForTransition(prev, next);
        out.push(m ? m.id : null);
        prev = next;
      }
      return out;
    };
    expect(run()).toEqual(run());
    // Spot-check the stream: null (first), nightfall, daybreak, dusk-settle,
    // (dusk→night: nightfall), daybreak.
    expect(run()).toEqual([
      null,
      "nightfall",
      "daybreak",
      "dusk-settle",
      "nightfall",
      "daybreak",
    ]);
  });
});
