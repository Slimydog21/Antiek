/**
 * ProceduralSky.test.tsx — SPR-04 milestone 5 (deterministic offline fallback),
 * ELEVATED in ALC SPR-05 M2 (layered atmosphere per dayPart anchor).
 *
 * This is the path CI + the sandbox ALWAYS take (no Krea key), so it IS the
 * experience. It must be DELIBERATE + ATMOSPHERIC (multi-stop sky + horizon glow
 * + seeded stars at night/dusk + aerial haze) and BYTE-STABLE for a given mood,
 * so a snapshot pins it.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { ProceduralSky } from "./ProceduralSky";
import type { SceneMood } from "../mood";

afterEach(() => cleanup());

const DAWN: SceneMood = { dayPart: "dawn", weather: "snow" };
const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const DUSK: SceneMood = { dayPart: "dusk", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

describe("ProceduralSky — layered atmosphere (M2)", () => {
  it("renders the layered atmosphere for day (snapshot)", () => {
    const { container } = render(<ProceduralSky mood={DAY} />);
    const sky = container.querySelector('[data-testid="procedural-sky"]');
    expect(sky).toBeTruthy();
    // A composed sky: a multi-stop gradient LAYER (token vars, inline style),
    // not a placeholder grey, not the old single 3-stop Tailwind class.
    const grad = container.querySelector('[data-sky-layer="gradient"]') as HTMLElement;
    expect(grad).toBeTruthy();
    expect(grad.getAttribute("style")).toContain("var(--scene-sky-day-0)");
    // A horizon glow layer.
    expect(container.querySelector('[data-sky-layer="glow"]')).toBeTruthy();
    // Three peak bands (far/mid/near silhouettes) — unchanged count.
    expect(container.querySelectorAll("[data-band] > path").length).toBeGreaterThanOrEqual(3);
    // An aerial-haze veil over the far band.
    expect(container.querySelector('[data-sky-layer="haze"]')).toBeTruthy();
    expect(container.firstChild).toMatchSnapshot();
  });

  it("is byte-stable across renders for the same mood (incl. seeded stars)", () => {
    const a = render(<ProceduralSky mood={NIGHT} />).container.innerHTML;
    cleanup();
    const b = render(<ProceduralSky mood={NIGHT} />).container.innerHTML;
    expect(a).toBe(b);
  });

  it("paints DETERMINISTIC seeded stars at night + dusk, none by day/dawn", () => {
    const night = render(<ProceduralSky mood={NIGHT} />).container;
    expect(night.querySelector('[data-sky-layer="stars"]')).toBeTruthy();
    expect(night.querySelectorAll('[data-sky-layer="stars"] circle').length).toBeGreaterThan(0);
    cleanup();

    const dusk = render(<ProceduralSky mood={DUSK} />).container;
    expect(dusk.querySelector('[data-sky-layer="stars"]')).toBeTruthy();
    cleanup();

    const day = render(<ProceduralSky mood={DAY} />).container;
    expect(day.querySelector('[data-sky-layer="stars"]')).toBeNull();
    cleanup();

    const dawn = render(<ProceduralSky mood={DAWN} />).container;
    expect(dawn.querySelector('[data-sky-layer="stars"]')).toBeNull();
  });

  it("each dayPart anchor paints a DISTINCT sky (the SPR-06 drift anchors)", () => {
    const skies = [DAWN, DAY, DUSK, NIGHT].map((m) => {
      const c = render(<ProceduralSky mood={m} />).container;
      const grad = c.querySelector('[data-sky-layer="gradient"]') as HTMLElement;
      const style = grad.getAttribute("style") ?? "";
      cleanup();
      return style;
    });
    // Four distinct gradient definitions — no two anchors collapse.
    expect(new Set(skies).size).toBe(4);
  });

  it("night mood is tagged by dayPart + moodKey", () => {
    const { container } = render(<ProceduralSky mood={NIGHT} />);
    const sky = container.querySelector('[data-testid="procedural-sky"]') as HTMLElement;
    expect(sky.getAttribute("data-daypart")).toBe("night");
    expect(sky.getAttribute("data-mood")).toBe("night|snow");
  });
});
