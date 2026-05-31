/**
 * mood.test.ts — SPR-04 milestone 7: the theme→mood mapping is the documented
 * contract, and it drives the Krea scene-state. We reuse the app's existing
 * day/night signal (prefers-color-scheme); these tests pin the mapping.
 */
import { describe, expect, it } from "vitest";

import {
  moodFromTheme,
  moodKey,
  sceneStateFromMood,
} from "./mood";

describe("theme → mood mapping", () => {
  it("light OS theme → day mood", () => {
    expect(moodFromTheme(false).dayPart).toBe("day");
  });

  it("dark OS theme → night mood", () => {
    expect(moodFromTheme(true).dayPart).toBe("night");
  });

  it("weather defaults to the snow motif (Herzog Antarctic)", () => {
    expect(moodFromTheme(false).weather).toBe("snow");
    expect(moodFromTheme(true).weather).toBe("snow");
  });
});

describe("mood → Krea scene-state", () => {
  it("night mood maps to dayNight=night so the placeholder darkens + the prompt shifts", () => {
    const s = sceneStateFromMood(moodFromTheme(true));
    expect(s.dayNight).toBe("night");
    expect(s.mood).toBe("night");
  });

  it("day mood maps to dayNight=day", () => {
    const s = sceneStateFromMood(moodFromTheme(false));
    expect(s.dayNight).toBe("day");
  });

  it("snow weather maps to a winter season axis", () => {
    expect(sceneStateFromMood(moodFromTheme(false)).season).toBe("winter");
  });
});

describe("moodKey", () => {
  it("is stable + distinguishes day/night", () => {
    expect(moodKey(moodFromTheme(false))).toBe("day|snow");
    expect(moodKey(moodFromTheme(true))).toBe("night|snow");
  });
});
