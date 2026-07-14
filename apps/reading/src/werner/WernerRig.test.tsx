/**
 * WernerRig.test.tsx — the labelled station rig (SPR-06 M1 → SPR-24).
 *
 * What this proves at the UNIT level (the deterministic half):
 *  - the rig renders one canonical-derived station body (not a fork);
 *  - the station body is decorative beneath one labelled wrapper;
 *  - the rod exists, pivots from the grip, tapers, and is token-coloured;
 *  - the rod flexes under bend and rests straight under reduced motion;
 *  - the idle fishing marks (line + fish) are hidden at rest;
 *  - NO vector feet or flippers exist (removed in SPR-24);
 *  - the layer order is rod → authored body → line/fish (foreground);
 *  - the authored body is the ONLY importer of the station fishing PNG
 *    (import boundary);
 *  - geometry constants (ROD_BUTT, ROD_TIP) are unchanged.
 *
 * What this DELIBERATELY does NOT prove here (rigor #1 — honest about the
 * limit): "the rendered rod is LONGER on screen" + "the line's first point
 * lands on the tip in real pixels" — those are the e2e RULE-2 gate
 * (e2e/_werner/rod-in-hand.spec.ts), since jsdom lays nothing out. This pins
 * the structural contract; the browser gate is the durable proof of length +
 * join.
 */
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { PNG } from "pngjs";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import WernerRig from "./WernerRig";
import { ROD_BUTT_LOCAL, ROD_TIP_LOCAL } from "./fishingLineGeometry";

/**
 * usePrefersReducedMotion reads window.matchMedia, which jsdom lacks. Stub it as
 * the hotkey/ad/penguin suites do. `setReducedMotion(b)` lets the SPR-04 rest-
 * pose test flip the preference; default is motion-allowed (false).
 */
let reducedMotion = false;
function setReducedMotion(v: boolean): void {
  reducedMotion = v;
}
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
  setReducedMotion(false);
});

describe("WernerRig (SPR-06 M1 → SPR-24)", () => {
  it("frames the exact canonical pixels at the native 64px contract", () => {
    const png = PNG.sync.read(
      readFileSync(
        resolve(
          "src/brand/werner/poses/werner_station_fishing_v1_transparent.png",
        ),
      ),
    );
    expect([png.width, png.height]).toEqual([1024, 1024]);
    let minX = png.width;
    let minY = png.height;
    let maxX = -1;
    let maxY = -1;
    for (let y = 0; y < png.height; y += 1) {
      for (let x = 0; x < png.width; x += 1) {
        if (png.data[(y * png.width + x) * 4 + 3] === 0) continue;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
    }
    const native = {
      left: (minX / png.width) * 64,
      top: (minY / png.height) * 64,
      width: ((maxX - minX + 1) / png.width) * 64,
      height: ((maxY - minY + 1) / png.height) * 64,
      bottom: ((maxY + 1) / png.height) * 64,
    };
    expect(native.width).toBeGreaterThanOrEqual(38);
    expect(native.width).toBeLessThanOrEqual(46);
    expect(native.height).toBeGreaterThanOrEqual(50);
    expect(native.height).toBeLessThanOrEqual(56);
    expect(native.top).toBeGreaterThanOrEqual(2);
    expect(native.bottom).toBeGreaterThanOrEqual(57);
    expect(native.bottom).toBeLessThanOrEqual(62);
    for (let x = 0; x < png.width; x += 1) {
      expect(png.data[x * 4 + 3]).toBe(0);
      expect(png.data[((png.height - 1) * png.width + x) * 4 + 3]).toBe(0);
    }
    for (let y = 0; y < png.height; y += 1) {
      expect(png.data[(y * png.width) * 4 + 3]).toBe(0);
      expect(png.data[(y * png.width + png.width - 1) * 4 + 3]).toBe(0);
    }
  });

  it("renders one canonical-derived station body under one accessible wrapper", () => {
    const { container } = render(<WernerRig size={64} label="Project" />);
    // The Werner art (transparent variant) — a labelled role=img with an <img>.
    expect(container.querySelector("img")).not.toBeNull();
    // The authored station body — a decorative image with data-werner-authored-pose.
    const authored = container.querySelector(
      '[data-werner-authored-pose="stationFishing"]',
    );
    expect(authored, "the authored station body must be present").not.toBeNull();
  });

  it("owns NO motion source — no inline animation on any element (driven by ancestor classes)", () => {
    const { container } = render(<WernerRig size={64} />);
    // The rig must NOT set its own `animation` inline: motion comes ONLY from
    // the descendant selectors in waddle.css keyed off the roam's walk class.
    // A regression that inlined an animation (a second motion source) reddens.
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg!.style.animation, "the SVG must not own an inline animation").toBe(
      "",
    );
  });

  it("the SVG overlay is decorative (aria-hidden) — the Werner mark is the accessible name", () => {
    const { container } = render(<WernerRig size={64} label="Project" />);
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length, "there must be exactly 2 SVGs (rod + line/fish)").toBe(2);
    for (const svg of svgs) {
      expect(svg.getAttribute("aria-hidden")).toBe("true");
    }
    // The single accessible label lives on the Werner mark.
    expect(container.querySelector('[aria-label="Project"]')).not.toBeNull();
  });

  it("renders at the requested size (scales with the mascot footprint)", () => {
    const { container } = render(<WernerRig size={64} />);
    const svgs = container.querySelectorAll("svg");
    for (const svg of svgs) {
      expect(svg.getAttribute("width")).toBe("64");
      expect(svg.getAttribute("height")).toBe("64");
    }
  });
});

/**
 * SPR-24 — no vector feet or flippers remain.
 *
 * The feet + flippers are REMOVED from the SVG overlay. Their geometry is now
 * baked into the authored station body PNG. Locomotion is one whole-body
 * silhouette waddle, not alternating articulated limbs.
 */
describe("WernerRig — no vector limbs (SPR-24)", () => {
  it("renders zero vector foot elements", () => {
    const { container } = render(<WernerRig size={64} />);
    expect(container.querySelector(".werner-rig-foot-l")).toBeNull();
    expect(container.querySelector(".werner-rig-foot-r")).toBeNull();
  });

  it("renders zero vector flipper elements", () => {
    const { container } = render(<WernerRig size={64} />);
    expect(container.querySelector(".werner-rig-flipper-l")).toBeNull();
    expect(container.querySelector(".werner-rig-flipper-r")).toBeNull();
  });

  it("contains no fill using the --werner-foot token (feet are in the authored PNG now)", () => {
    const { container } = render(<WernerRig size={64} />);
    const allElements = container.querySelectorAll("[fill]");
    for (const el of allElements) {
      const fill = el.getAttribute("fill");
      expect(fill, `unexpected --werner-foot fill on a vector limb: ${fill}`).not.toBe(
        "var(--werner-foot)",
      );
    }
  });
});

/**
 * SPR-04 — the real rod, gripped behind the authored body.
 *
 * The DETERMINISTIC half: the rod <g> exists, pivots from the grip, the rod is
 * token-coloured (no hex), and reduced motion holds a straight neutral rest
 * pose. What this does NOT prove (rigor #1): "the rendered rod is LONGER on
 * screen" + "the line's first point lands on the tip in real pixels" — those are
 * the e2e RULE-2 gate.
 */
describe("WernerRig — the rod behind the authored body (SPR-04/24)", () => {
  it("renders the rod as a structured <g> that pivots from the GRIP (transform-origin at the butt)", () => {
    const { container } = render(<WernerRig size={64} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    expect(rod, "the rod <g> is missing").not.toBeNull();
    // Pivot at the grip = ROD_BUTT (45,34) — so a future cast swings it from the
    // hand, not the body centre.
    expect(rod!.style.transformOrigin).toBe(
      `${ROD_BUTT_LOCAL.x}px ${ROD_BUTT_LOCAL.y}px`,
    );
  });

  it("the rod is token-coloured — no raw hex on the rod paint", () => {
    const { container } = render(<WernerRig size={64} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    expect(rod).not.toBeNull();
    const painted = rod!.querySelectorAll("[stroke], [fill]");
    expect(painted.length).toBeGreaterThan(0);
    painted.forEach((el) => {
      const stroke = el.getAttribute("stroke");
      const fill = el.getAttribute("fill");
      for (const paint of [stroke, fill]) {
        if (paint && paint !== "none") {
          expect(paint, `raw colour on the rod: ${paint}`).toMatch(/var\(--werner-/);
          expect(paint).not.toMatch(/#[0-9a-fA-F]{3,8}/);
        }
      }
    });
  });

  it("the shaft TAPERS — the butt segment is wider than the tip segment", () => {
    const { container } = render(<WernerRig size={64} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    const widths = Array.from(rod!.querySelectorAll("path[stroke-width]")).map(
      (p) => Number(p.getAttribute("stroke-width")),
    );
    expect(widths.length, "the rod has no shaft segments").toBeGreaterThan(1);
    // The first (butt) segment must be strictly wider than the last (tip).
    expect(widths[0]).toBeGreaterThan(widths[widths.length - 1]);
  });

  it("rests STRAIGHT under reduced motion — the bend collapses (no mid-cast flex)", () => {
    setReducedMotion(true);
    const { container } = render(<WernerRig size={64} bend={6} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    const segs = Array.from(rod!.querySelectorAll("path[d]")).map((p) =>
      p.getAttribute("d"),
    );
    expect(segs.length).toBeGreaterThan(1);
    // A straight rod: every segment endpoint lies on the butt→tip chord (within
    // a hair of float noise). Bend would bow them off the chord.
    const ax = ROD_TIP_LOCAL.x - ROD_BUTT_LOCAL.x;
    const ay = ROD_TIP_LOCAL.y - ROD_BUTT_LOCAL.y;
    const len = Math.hypot(ax, ay);
    for (const d of segs) {
      const pts = d!.match(/-?\d+(\.\d+)?/g)!.map(Number);
      for (let i = 0; i < pts.length; i += 2) {
        const x = pts[i];
        const y = pts[i + 1];
        // Perpendicular distance from the point to the butt→tip line.
        const perp =
          Math.abs((x - ROD_BUTT_LOCAL.x) * ay - (y - ROD_BUTT_LOCAL.y) * ax) /
          len;
        expect(
          perp,
          `reduced-motion rod is not straight (point ${x},${y} bows ${perp.toFixed(2)} off the chord)`,
        ).toBeLessThan(0.01);
      }
    }
  });

  it("FLEXES when bend is applied with motion allowed (the rest-pose guard is conditional, not always-on)", () => {
    // Counterpart to the reduced-motion test: prove bend actually bows the shaft
    // when motion IS allowed — otherwise the straight-rest test could pass
    // vacuously (a rod that never bends).
    const { container } = render(<WernerRig size={64} bend={6} />);
    const rod = container.querySelector("[data-werner-rod]") as SVGGElement | null;
    const segs = Array.from(rod!.querySelectorAll("path[d]")).map((p) =>
      p.getAttribute("d"),
    );
    const ax = ROD_TIP_LOCAL.x - ROD_BUTT_LOCAL.x;
    const ay = ROD_TIP_LOCAL.y - ROD_BUTT_LOCAL.y;
    const len = Math.hypot(ax, ay);
    let maxPerp = 0;
    for (const d of segs) {
      const pts = d!.match(/-?\d+(\.\d+)?/g)!.map(Number);
      for (let i = 0; i < pts.length; i += 2) {
        const perp =
          Math.abs(
            (pts[i] - ROD_BUTT_LOCAL.x) * ay - (pts[i + 1] - ROD_BUTT_LOCAL.y) * ax,
          ) / len;
        if (perp > maxPerp) maxPerp = perp;
      }
    }
    expect(maxPerp, "bend did not bow the shaft off the chord").toBeGreaterThan(1);
  });
});

/**
 * SPR-24 — exact layer order.
 *
 * The spec mandates: rod → authored body → code line/fish marks. DOM order
 * determines painting order for absolutely-positioned siblings. The rod SVG
 * must come first (behind), the authored body in the middle, and the line/fish
 * SVG last (foreground).
 */
describe("WernerRig — exact layer order (SPR-24)", () => {
  it("DOM order is: rod SVG → authored body → line/fish SVG", () => {
    const { container } = render(<WernerRig size={64} />);
    const wrapper = container.querySelector("[data-werner-rig]");
    expect(wrapper).not.toBeNull();
    const children = Array.from(wrapper!.childNodes).filter(
      (n) => n.nodeType === Node.ELEMENT_NODE,
    ) as HTMLElement[];
    expect(children.length).toBe(3);
    expect(wrapper!.getAttribute("role")).toBe("img");
    expect(children[0].tagName.toLowerCase()).toBe("svg");
    expect(children[0].querySelector("[data-werner-rod]")).not.toBeNull();
    expect(children[1].tagName).toBe("IMG");
    expect(children[1].getAttribute("data-werner-authored-pose")).toBe(
      "stationFishing",
    );
    expect(children[2].tagName.toLowerCase()).toBe("svg");
    expect(children[2].querySelector(".werner-rig-line")).not.toBeNull();
    expect(children[2].querySelector(".werner-rig-fish")).not.toBeNull();
  });
});

/**
 * SPR-24 — import boundary.
 *
 * The station fishing PNG must ONLY be imported by WernerAuthoredPose.
 * WernerRig must NOT import the PNG directly — it consumes it through the
 * WernerAuthoredPose abstraction.
 */
describe("WernerRig — import boundary (SPR-24)", () => {
  it("has exactly one runtime importer: WernerAuthoredPose", () => {
    const runtimeFiles: string[] = [];
    const walk = (directory: string): void => {
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const path = resolve(directory, entry.name);
        if (entry.isDirectory()) walk(path);
        else if (/\.(ts|tsx)$/.test(entry.name) && !/\.(test|stories)\./.test(entry.name)) {
          runtimeFiles.push(path);
        }
      }
    };
    walk(resolve("src"));
    const importers = runtimeFiles.filter((path) =>
      readFileSync(path, "utf8").includes("werner_station_fishing_v1_transparent.png"),
    );
    expect(importers.map((path) => path.replace(`${resolve("src")}/`, ""))).toEqual([
      "brand/werner/WernerAuthoredPose.tsx",
    ]);
  });
});

describe("WernerRig — idle fishing marks hidden at rest (SPR-05)", () => {
  it("hides the idle line + fish by default; only the .werner-fishing loop reveals them", () => {
    const { container } = render(<WernerRig size={64} />);
    const line = container.querySelector(".werner-rig-line");
    const fish = container.querySelector(".werner-rig-fish");
    expect(line, "idle line node should exist").not.toBeNull();
    expect(fish, "fish node should exist").not.toBeNull();
    // No .werner-fishing ancestor here — the loop is OFF, which is the production
    // default (ice flag off, reduced motion, or any rest moment). Both marks MUST
    // be opacity 0 by default, else a teal fish + line dangle off a resting
    // Werner. The .werner-fishing keyframes animate opacity up only while the gag
    // runs.
    expect(line!.getAttribute("opacity")).toBe("0");
    expect(fish!.getAttribute("opacity")).toBe("0");
  });
});

/**
 * SPR-24 — geometry constants unchanged.
 *
 * The rod butt/tip contract must remain exactly (45,34) and (66,5).
 * Any drift breaks the shared contract with WernerFishingLayer.
 */
describe("WernerRig — geometry constants unchanged (SPR-24)", () => {
  it("ROD_BUTT is exactly (45, 34)", () => {
    expect(ROD_BUTT_LOCAL).toEqual({ x: 45, y: 34 });
  });

  it("ROD_TIP is exactly (66, 5)", () => {
    expect(ROD_TIP_LOCAL).toEqual({ x: 66, y: 5 });
  });
});
