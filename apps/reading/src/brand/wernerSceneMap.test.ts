/**
 * wernerSceneMap.test.ts — the scene-reactivity map is total, deterministic,
 * restrained, and gap-honest (ALC SPR-07 M1).
 *
 * The four guards, each a countable assertion:
 *   1. EXHAUSTIVE   — a defined cue for every one of the 8 SceneMood states; no
 *                     fall-through to undefined.
 *   2. RESTRAINT    — every cue's mood is one of the four sanctioned WernerMoods;
 *                     the map can never emit a fifth mood Werner.tsx would throw on.
 *   3. DETERMINISTIC— same scene_key ⇒ byte-identical cue across re-derivation
 *                     (double-derive + deep-equal), and the cue's sceneKey
 *                     matches moodKey(mood).
 *   4. GAP-HONEST   — every POSE_GAPS entry names a real scene state and a
 *                     sanctioned fallback mood, and the table actually USES that
 *                     fallback for that state (no gap claimed that the table
 *                     contradicts).
 */
import { describe, expect, it } from "vitest";

import {
  wernerForScene,
  wernerMoodForScene,
  POSE_GAPS,
  type WernerSceneCue,
} from "./wernerSceneMap";
import { moodKey, type DayPart, type Weather, type SceneMood } from "../scene/mood";

const DAY_PARTS: readonly DayPart[] = ["dawn", "day", "dusk", "night"];
const WEATHERS: readonly Weather[] = ["clear", "snow"];
const SANCTIONED = new Set(["idle", "thinking", "empty", "celebrate"]);

/** The full cross-product of scene states — the universe the map must cover. */
const ALL_MOODS: readonly SceneMood[] = DAY_PARTS.flatMap((dayPart) =>
  WEATHERS.map((weather) => ({ dayPart, weather })),
);

describe("wernerSceneMap — total + restrained scene reactivity (M1)", () => {
  it("EXHAUSTIVE: a defined cue for every one of the 8 scene states, never undefined", () => {
    expect(ALL_MOODS).toHaveLength(DAY_PARTS.length * WEATHERS.length); // 4 × 2 = 8
    for (const mood of ALL_MOODS) {
      const cue = wernerForScene(mood);
      expect(cue, `cue for ${moodKey(mood)}`).toBeDefined();
      expect(cue.mood, `mood for ${moodKey(mood)}`).toBeDefined();
      expect(cue.reason, `reason for ${moodKey(mood)}`).toBeTruthy();
    }
  });

  it("RESTRAINT: every cue maps to one of the four sanctioned Werner moods (no 5th)", () => {
    for (const mood of ALL_MOODS) {
      const cue = wernerForScene(mood);
      expect(
        SANCTIONED.has(cue.mood),
        `${moodKey(mood)} → "${cue.mood}" must be a sanctioned mood`,
      ).toBe(true);
    }
  });

  it("DETERMINISTIC: same scene_key ⇒ byte-identical cue (double-derive deep-equal)", () => {
    for (const mood of ALL_MOODS) {
      const first = wernerForScene(mood);
      // Re-derive from a fresh object with the same fields (proves the function
      // keys on VALUE, not identity — no hidden per-call state).
      const second = wernerForScene({ ...mood });
      expect(second).toEqual(first);
      // And the cue's recorded scene_key matches the canonical moodKey, so a
      // consumer detecting a transition off cue.sceneKey agrees with the scene.
      expect(first.sceneKey).toBe(moodKey(mood));
    }
  });

  it("DETERMINISTIC: byte-stable as a serialized snapshot per scene state", () => {
    const snapshot: Record<string, WernerSceneCue> = {};
    for (const mood of ALL_MOODS) snapshot[moodKey(mood)] = wernerForScene(mood);
    // Serialize → re-derive → serialize: identical bytes (no Date/RNG drift).
    const a = JSON.stringify(snapshot);
    const snapshot2: Record<string, WernerSceneCue> = {};
    for (const mood of ALL_MOODS) snapshot2[moodKey(mood)] = wernerForScene(mood);
    const b = JSON.stringify(snapshot2);
    expect(b).toBe(a);
  });

  it("wernerMoodForScene is the thin mood accessor, agreeing with the cue", () => {
    for (const mood of ALL_MOODS) {
      expect(wernerMoodForScene(mood)).toBe(wernerForScene(mood).mood);
    }
  });

  it("GAP-HONEST: every recorded gap names a real state + the table actually uses its fallback", () => {
    for (const gap of POSE_GAPS) {
      // The gap's scene_key is one of the real 8 states.
      const matched = ALL_MOODS.find((m) => moodKey(m) === gap.sceneKey);
      expect(matched, `gap scene_key "${gap.sceneKey}" must be a real state`).toBeDefined();
      // The fallback it claims is what the table actually emits (no contradiction).
      expect(wernerForScene(matched as SceneMood).mood).toBe(gap.fallbackMood);
      // And the fallback is itself sanctioned + the gap carries turnover detail.
      expect(SANCTIONED.has(gap.fallbackMood)).toBe(true);
      expect(gap.wantedPose).toBeTruthy();
      expect(gap.note).toBeTruthy();
    }
  });

  it("the emitting states today (day|snow, night|snow) both resolve to idle (restful, scene-consistent)", () => {
    // mood.ts moodFromTheme emits only day|snow + night|snow today; both should
    // read as Werner calmly present (idle), not a system-state pose.
    expect(wernerMoodForScene({ dayPart: "day", weather: "snow" })).toBe("idle");
    expect(wernerMoodForScene({ dayPart: "night", weather: "snow" })).toBe("idle");
  });
});
