/**
 * snapshot-matrix.test.tsx — the DETERMINISTIC scene-mood-matrix harness
 * (ALC SPR-05, milestone M1).
 *
 * WHY THIS EXISTS (and why NOT the Storybook scene story): the Storybook scene
 * story `workspace-demo--scene` is filterShot-EXCLUDED from the visual-regression
 * rail (`lostpixel.config.ts:51-54`) because the framer-motion spring is
 * nondeterministic. So the matrix "before/after photo" can NOT lean on it. This
 * harness instead renders the scene's DETERMINISTIC, memoized layers through the
 * FROZEN path (no rAF, no Date.now, no Math.random) and serialises the rendered
 * DOM to disk — a byte-stable artifact for every cell in the full state space.
 *
 * It renders TWO things per cell:
 *   1. ProceduralSky (the atmosphere + peaks) — the picture every user sees in
 *      the always-on procedural-first floor. Memoized + seeded → byte-stable.
 *   2. Mountainscape (the SPR-05 depth planes) — likewise static + seeded.
 * The serialised HTML is the inspectable evidence the M1 audit + the parity
 * auditor cite per cell (markup-level "screenshot": exact gradient stops, plane
 * recession, peak fills, star placement — everything a PNG would show, in a
 * diffable form the snapshot rail can't give us for the live scene).
 *
 * DETERMINISM CONTRACT: the canvas painters (Clouds/Snow) are NOT rendered here
 * — jsdom has no canvas, and their determinism is already proven byte-for-byte
 * in field.test.ts (makeSnow/makeClouds/snowAt/cloudX pure). This harness owns
 * the CSS/SVG floor (sky + peaks + depth planes), which is what M1/M2/M4 elevate.
 *
 * STATE SPACE (derived from mood.ts, NOT assumed):
 *   DayPart  = dawn | day | dusk | night          (4)
 *   Weather  = clear | snow                        (2)
 *   => 8 TYPE cells. moodKey() = `${dayPart}|${weather}`.
 * Of these 8, the architecture activates 4 (× snow) — see the audit doc for the
 * emitted / drift-anchor / reserved split. We render ALL 8 (no sampling) so a
 * reserved cell that regressed is caught, exactly as the rigor #1/#3 count demands.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { ProceduralSky } from "../layers/ProceduralSky";
import { Mountainscape } from "../layers/Mountainscape";
import type { DayPart, SceneMood, Weather } from "../mood";
import { moodKey } from "../mood";

afterEach(() => cleanup());

const DAY_PARTS: DayPart[] = ["dawn", "day", "dusk", "night"];
const WEATHERS: Weather[] = ["clear", "snow"];

/** The full derived state space — every cell, no sampling. */
const CELLS: SceneMood[] = DAY_PARTS.flatMap((dayPart) =>
  WEATHERS.map((weather) => ({ dayPart, weather })),
);

const OUT_DIR = join(__dirname, "artifacts");

describe("scene mood matrix — deterministic before/after harness (M1)", () => {
  it("enumerates the FULL 8-cell state space (no sampling)", () => {
    expect(CELLS).toHaveLength(8);
    const keys = CELLS.map(moodKey).sort();
    expect(keys).toEqual(
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

  it("renders every cell deterministically + writes a diffable artifact per cell", () => {
    if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });

    for (const mood of CELLS) {
      const key = moodKey(mood);
      // Render the atmosphere (sky+peaks) and the depth planes for this cell.
      // Both are memoized-deterministic — no clock, no rAF, no randomness.
      const sky = render(<ProceduralSky mood={mood} />).container.innerHTML;
      cleanup();
      const planes = render(<Mountainscape mood={mood} />).container.innerHTML;
      cleanup();

      const html = `<!-- cell: ${key} (deterministic frozen render) -->\n` +
        `<section data-cell="${key}">\n` +
        `  <div class="atmosphere">${sky}</div>\n` +
        `  <div class="depth">${planes}</div>\n` +
        `</section>\n`;
      writeFileSync(join(OUT_DIR, `${key.replace("|", "_")}.html`), html);
    }
    // 8 artifacts written — one per cell.
    expect(CELLS).toHaveLength(8);
  });

  it("is BYTE-STABLE per cell across a double render (star/plane determinism)", () => {
    // The rigor #3 determinism gate: double-render byte-diff. We assert it on
    // ALL cells (not just 3) since the harness is cheap and the stars/planes
    // are the new seeded content M2/M4 add.
    for (const mood of CELLS) {
      const a = render(<ProceduralSky mood={mood} />).container.innerHTML;
      cleanup();
      const b = render(<ProceduralSky mood={mood} />).container.innerHTML;
      cleanup();
      expect(a, `ProceduralSky[${moodKey(mood)}] must be byte-stable`).toBe(b);

      const pa = render(<Mountainscape mood={mood} />).container.innerHTML;
      cleanup();
      const pb = render(<Mountainscape mood={mood} />).container.innerHTML;
      cleanup();
      expect(pa, `Mountainscape[${moodKey(mood)}] must be byte-stable`).toBe(pb);
    }
  });
});
