/**
 * Mountainscape.test.tsx — ALC SPR-05 M4: the foreground depth layer.
 *
 * Proves the depth contract SPR-06 builds on:
 *   - ≥3 named depth planes (far/mid/near) render, each a seeded ridge;
 *   - value/saturation recession is encoded (far hazed, near un-veiled);
 *   - the parallax-depth seam ordering is far < mid < near (recession);
 *   - the planes are BYTE-STABLE per mood (determinism gate);
 *   - the typed transform SEAM is honoured (a passed transform lands on the
 *     plane group) — but the component animates NOTHING on its own.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { Mountainscape, PLANE_DEPTHS } from "./Mountainscape";
import type { SceneMood } from "../mood";

afterEach(() => cleanup());

const DAY: SceneMood = { dayPart: "day", weather: "snow" };
const NIGHT: SceneMood = { dayPart: "night", weather: "snow" };

describe("Mountainscape — depth planes (M4)", () => {
  it("renders three named depth planes (far/mid/near)", () => {
    const { container } = render(<Mountainscape mood={DAY} />);
    const roles = Array.from(container.querySelectorAll("[data-plane]")).map((g) =>
      g.getAttribute("data-plane"),
    );
    expect(roles).toEqual(["far", "mid", "near"]);
  });

  it("encodes aerial recession: the FAR plane is hazed, the NEAR plane is not", () => {
    const { container } = render(<Mountainscape mood={DAY} />);
    expect(container.querySelector('[data-plane-haze="far"]')).toBeTruthy();
    expect(container.querySelector('[data-plane-haze="near"]')).toBeNull();
  });

  it("parallax depths recede monotonically far < mid < near", () => {
    expect(PLANE_DEPTHS).toHaveLength(3);
    expect(PLANE_DEPTHS[0]).toBeLessThan(PLANE_DEPTHS[1]);
    expect(PLANE_DEPTHS[1]).toBeLessThan(PLANE_DEPTHS[2]);
    expect(PLANE_DEPTHS[2]).toBeLessThanOrEqual(1);
  });

  it("is byte-stable across renders for the same mood (determinism)", () => {
    const a = render(<Mountainscape mood={NIGHT} />).container.innerHTML;
    cleanup();
    const b = render(<Mountainscape mood={NIGHT} />).container.innerHTML;
    expect(a).toBe(b);
  });

  it("day and night render DISTINCT fills (the planes track time-of-day)", () => {
    const day = render(<Mountainscape mood={DAY} />).container.innerHTML;
    cleanup();
    const night = render(<Mountainscape mood={NIGHT} />).container.innerHTML;
    expect(day).not.toBe(night);
  });

  it("honours the typed transform SEAM (SPR-06 drives parallax; static here)", () => {
    const seams = [
      { transform: "translateY(2px)" },
      { transform: "translateY(4px)" },
      { transform: "translateY(8px)" },
    ];
    const { container } = render(<Mountainscape mood={DAY} seams={seams} />);
    const groups = Array.from(container.querySelectorAll("[data-plane]")) as HTMLElement[];
    expect(groups[0].style.transform).toBe("translateY(2px)");
    expect(groups[2].style.transform).toBe("translateY(8px)");
    // willChange is hinted only when a transform is supplied (compositor hint
    // for SPR-06, not an animation).
    expect(groups[0].style.willChange).toBe("transform");
  });

  it("with NO seams the planes carry no transform (a static composed frame)", () => {
    const { container } = render(<Mountainscape mood={DAY} />);
    const groups = Array.from(container.querySelectorAll("[data-plane]")) as HTMLElement[];
    for (const g of groups) {
      expect(g.style.transform).toBe("");
      expect(g.style.willChange).toBe("");
    }
  });
});
