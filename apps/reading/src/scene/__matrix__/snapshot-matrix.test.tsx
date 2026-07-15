import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { ProceduralSky } from "../layers/ProceduralSky";
import type { DayPart, SceneMood, Weather } from "../mood";
import { moodKey } from "../mood";
import { LANDSCAPE_PALETTE } from "../landscapePalette";

afterEach(() => cleanup());

const DAY_PARTS: DayPart[] = ["dawn", "day", "dusk", "night"];
const WEATHERS: Weather[] = ["clear", "snow"];
const CELLS: SceneMood[] = DAY_PARTS.flatMap((dayPart) =>
  WEATHERS.map((weather) => ({ dayPart, weather })),
);
const OUT_DIR = join(__dirname, "artifacts");

describe("scene state matrix artifacts", () => {
  it("enumerates the full day-part and weather grid", () => {
    expect(CELLS.map(moodKey).sort()).toEqual(
      [
        "dawn|clear",
        "dawn|snow",
        "day|clear",
        "day|snow",
        "dusk|clear",
        "dusk|snow",
        "night|clear",
        "night|snow",
      ].sort(),
    );
  });

  it("regenerates deterministic HTML artifacts for every scene state", () => {
    if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });

    for (const mood of CELLS) {
      const key = moodKey(mood);
      const sky = render(<ProceduralSky mood={mood} />).container.innerHTML;
      cleanup();
      writeFileSync(
        join(OUT_DIR, `${key.replace("|", "_")}.html`),
        `<!-- cell: ${key} (current main procedural floor, frozen matrix render) -->\n` +
          `<section data-cell="${key}">\n` +
          `  <div class="atmosphere">${sky}</div>\n` +
          `</section>\n`,
      );
    }

    expect(CELLS).toHaveLength(8);
  });

  it("is byte-stable across double render for every state", () => {
    for (const mood of CELLS) {
      const first = render(<ProceduralSky mood={mood} />).container.innerHTML;
      cleanup();
      const second = render(<ProceduralSky mood={mood} />).container.innerHTML;
      cleanup();
      expect(first, `${moodKey(mood)} matrix render must be deterministic`).toBe(second);
    }
  });
});

describe("landscape palette honesty (ATP-01 milestone 4)", () => {
  it("all four daypart palettes are unique — no two share the same six-role tuple", () => {
    const tuples = DAY_PARTS.map(
      (dp) => JSON.stringify(LANDSCAPE_PALETTE[dp]),
    );
    const unique = new Set(tuples);
    expect(unique.size).toBe(4);
  });

  it("dawn and day have distinct skyHorizon tokens", () => {
    expect(LANDSCAPE_PALETTE.dawn.sky).not.toBe(LANDSCAPE_PALETTE.day.sky);
  });

  it("dusk and night have distinct skyTop and skyHorizon tokens", () => {
    expect(LANDSCAPE_PALETTE.dusk.sky).not.toBe(LANDSCAPE_PALETTE.night.sky);
    expect(LANDSCAPE_PALETTE.dusk.ridges).not.toEqual(
      LANDSCAPE_PALETTE.night.ridges,
    );
  });

  it("dawn/day sky gradient renders differently in the DOM", () => {
    const dawnSky = render(
      <ProceduralSky mood={{ dayPart: "dawn", weather: "snow" }} />,
    ).container.querySelector('[data-testid="procedural-sky"]');
    cleanup();
    const daySky = render(
      <ProceduralSky mood={{ dayPart: "day", weather: "snow" }} />,
    ).container.querySelector('[data-testid="procedural-sky"]');
    cleanup();
    expect(dawnSky!.className).not.toBe(daySky!.className);
  });

  it("dusk/night sky gradient renders differently in the DOM", () => {
    const duskSky = render(
      <ProceduralSky mood={{ dayPart: "dusk", weather: "snow" }} />,
    ).container.querySelector('[data-testid="procedural-sky"]');
    cleanup();
    const nightSky = render(
      <ProceduralSky mood={{ dayPart: "night", weather: "snow" }} />,
    ).container.querySelector('[data-testid="procedural-sky"]');
    cleanup();
    expect(duskSky!.className).not.toBe(nightSky!.className);
  });
});
