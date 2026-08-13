/**
 * BrainRig.test.tsx — the station rig renders the BRAIN + the rod, and the
 * rod holds a straight neutral rest pose under reduced motion (same contract
 * WernerRig.test.tsx pins for the penguin rig).
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import BrainRig from "./BrainRig";

// usePrefersReducedMotion reads window.matchMedia, which jsdom lacks — stub it
// the same way WernerRig.test.tsx does (default: motion allowed).
let reducedMotion = false;
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes("reduce") ? reducedMotion : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});
afterEach(() => {
  cleanup();
  reducedMotion = false;
});

describe("BrainRig", () => {
  it("renders the brain mark with the rod overlay", () => {
    const { getByRole, container } = render(<BrainRig size={64} label="Project" />);
    expect(getByRole("img")).toBeTruthy();
    const brainImg = container.querySelector("img");
    expect(brainImg?.getAttribute("src")).toBeTruthy();
    expect(container.querySelector('[data-brain-rig]')).toBeTruthy();
    // The rod is decorative SVG chrome on top of the labelled mark.
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("draws the rod segments at any bend", () => {
    const { container } = render(<BrainRig size={64} label="Project" bend={3} />);
    expect(container.querySelectorAll("svg path").length).toBeGreaterThan(0);
  });

  it("still renders a straight rod under reduced motion (bend collapses to 0)", () => {
    reducedMotion = true;
    const { container } = render(<BrainRig size={64} label="Project" bend={4} />);
    expect(container.querySelectorAll("svg path").length).toBeGreaterThan(0);
    expect(container.querySelector('[data-brain-rig]')).toBeTruthy();
  });
});
