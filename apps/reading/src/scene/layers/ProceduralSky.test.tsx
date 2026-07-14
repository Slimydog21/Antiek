/**
 * ProceduralSky.test.tsx — SPR-04 milestone 5: the deterministic offline
 * fallback. This is the path CI + the sandbox ALWAYS take (no Krea key). It
 * must be DELIBERATE (token gradient + seeded peak silhouette) and BYTE-STABLE
 * for a given mood, so a snapshot pins it.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { ProceduralSky } from "./ProceduralSky";
import type { SceneMood } from "../mood";

afterEach(() => cleanup());

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

describe("ProceduralSky — deterministic fallback", () => {
  it("renders a deliberate day sky + seeded peaks (snapshot)", () => {
    const { container } = render(<ProceduralSky mood={DAY} />);
    const sky = container.querySelector('[data-testid="procedural-sky"]');
    expect(sky).toBeTruthy();
    // It is a real gradient sky (token classes), not a placeholder grey.
    expect(sky!.className).toContain("bg-gradient-to-b");
    // Three peak bands (far/mid/near silhouettes).
    expect(container.querySelectorAll("path")).toHaveLength(3);
    expect(container.firstChild).toMatchSnapshot();
  });

  it("is byte-stable across renders for the same mood", () => {
    const a = render(<ProceduralSky mood={DAY} />).container.innerHTML;
    cleanup();
    const b = render(<ProceduralSky mood={DAY} />).container.innerHTML;
    expect(a).toBe(b);
  });

  it("night mood paints a distinct (darker) sky", () => {
    const { container } = render(<ProceduralSky mood={NIGHT} />);
    const sky = container.querySelector('[data-testid="procedural-sky"]');
    expect(sky!.className).toContain("from-space-2");
    expect(sky!.className).toContain("to-charcoal-2");
    expect(sky!.getAttribute("data-mood")).toBe("night|snow");
  });
});
