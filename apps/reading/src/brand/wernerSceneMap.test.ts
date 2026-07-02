import { describe, expect, it } from "vitest";

import {
  POSE_GAPS,
  wernerForScene,
  wernerMoodForScene,
  type ArtPresence,
} from "./wernerSceneMap";
import { moodKey, type DayPart, type SceneMood, type Weather } from "../scene/mood";

const DAY_PARTS = ["dawn", "day", "dusk", "night"] satisfies readonly DayPart[];
const WEATHERS = ["clear", "snow"] satisfies readonly Weather[];
const ART_PRESENCES = ["live", "fallback"] satisfies readonly ArtPresence[];
const WERNER_MOODS = ["idle", "thinking", "empty", "celebrate"] as const;

const ALL_SCENES: readonly SceneMood[] = DAY_PARTS.flatMap((dayPart) =>
  WEATHERS.map((weather) => ({ dayPart, weather })),
);

describe("wernerSceneMap", () => {
  it("is total over the imported SceneMood axes and live/fallback art presence", () => {
    for (const scene of ALL_SCENES) {
      for (const presence of ART_PRESENCES) {
        const cue = wernerForScene(scene, { isFallback: presence === "fallback" });
        expect(cue.sceneKey).toBe(moodKey(scene));
        expect(cue.artPresence).toBe(presence);
        expect(cue.reason).toBeTruthy();
        expect(cue.companionCopy).toBeTruthy();
      }
    }
  });

  it("emits only the four sanctioned Werner moods", () => {
    for (const scene of ALL_SCENES) {
      expect(WERNER_MOODS).toContain(wernerForScene(scene).mood);
      expect(WERNER_MOODS).toContain(wernerForScene(scene, { isFallback: true }).mood);
      expect(wernerMoodForScene(scene)).toBe(wernerForScene(scene).mood);
    }
  });

  it("keeps fallback states companionable, not alarming", () => {
    for (const scene of ALL_SCENES) {
      const cue = wernerForScene(scene, { isFallback: true });
      const text = `${cue.reason} ${cue.companionCopy}`.toLowerCase();
      expect(text).toContain("procedural");
      expect(text).not.toContain("error");
      expect(text).not.toContain("failed");
      expect(text).not.toContain("degraded");
      expect(text).not.toContain("sorry");
    }
  });

  it("records only real pose gaps and uses the stated fallback mood", () => {
    const realKeys = new Set(ALL_SCENES.map(moodKey));
    for (const gap of POSE_GAPS) {
      expect(realKeys.has(gap.sceneKey)).toBe(true);
      const scene = ALL_SCENES.find((candidate) => moodKey(candidate) === gap.sceneKey);
      expect(scene).toBeDefined();
      expect(wernerForScene(scene as SceneMood).mood).toBe(gap.fallbackMood);
      expect(gap.wantedPose).toBeTruthy();
      expect(gap.note).toBeTruthy();
    }
  });
});
