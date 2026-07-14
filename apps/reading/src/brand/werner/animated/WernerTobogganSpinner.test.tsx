import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { PNG } from "pngjs";

import WernerTobogganSpinner from "./WernerTobogganSpinner";

describe("WernerTobogganSpinner — SPR-23 authored toboggan pose", () => {
  it("ships a bounded alpha-clean body without chroma-key residue", () => {
    const path = resolve(
      "src/brand/werner/poses/werner_tobogganing_body_v2_transparent.png",
    );
    const png = PNG.sync.read(readFileSync(path));
    expect([png.width, png.height]).toEqual([1024, 1024]);

    let opaque = 0;
    let magenta = 0;
    for (let index = 0; index < png.data.length; index += 4) {
      const [r, g, b, a] = png.data.subarray(index, index + 4);
      if (a > 0 && r > 200 && g < 80 && b > 180) magenta += 1;
      if (a > 127) {
        opaque += 1;
      }
    }
    const coverage = opaque / (png.width * png.height);
    expect(coverage).toBeGreaterThanOrEqual(0.2);
    expect(coverage).toBeLessThanOrEqual(0.3);
    expect(magenta).toBe(0);

    const alphaAt = (x: number, y: number) =>
      png.data[(png.width * y + x) * 4 + 3];
    const borderAlpha = [
      ...Array.from({ length: png.width }, (_, x) => alphaAt(x, 0)),
      ...Array.from({ length: png.width }, (_, x) =>
        alphaAt(x, png.height - 1),
      ),
      ...Array.from({ length: png.height - 2 }, (_, y) => alphaAt(0, y + 1)),
      ...Array.from({ length: png.height - 2 }, (_, y) =>
        alphaAt(png.width - 1, y + 1),
      ),
    ];
    expect(borderAlpha.every((alpha) => alpha === 0)).toBe(true);

    const opaquePixels = new Set<string>();
    for (let y = 0; y < png.height; y += 1) {
      for (let x = 0; x < png.width; x += 1) {
        if (alphaAt(x, y) > 127) opaquePixels.add(`${x},${y}`);
      }
    }
    const frontier = [opaquePixels.values().next().value as string];
    opaquePixels.delete(frontier[0]);
    let connected = 0;
    while (frontier.length > 0) {
      const point = frontier.pop()!;
      connected += 1;
      const [x, y] = point.split(",").map(Number);
      for (const neighbor of [
        `${x - 1},${y}`,
        `${x + 1},${y}`,
        `${x},${y - 1}`,
        `${x},${y + 1}`,
      ]) {
        if (opaquePixels.delete(neighbor)) frontier.push(neighbor);
      }
    }
    expect(connected).toBe(opaque);
    expect(opaquePixels.size).toBe(0);
  });

  // ─── Source-import boundary (Acceptance gate 2) ─────────────────────
  describe("import boundary", () => {
    it("WernerAuthoredPose is the sole runtime importer of the toboggan body", () => {
      const sourceRoot = resolve("src");
      const sourceFiles = (directory: string): string[] =>
        readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
          const path = resolve(directory, entry.name);
          return entry.isDirectory()
            ? sourceFiles(path)
            : /\.[cm]?[jt]sx?$/.test(entry.name) && !entry.name.includes(".test.")
              ? [path]
              : [];
        });
      const importers = sourceFiles(sourceRoot).filter((path) =>
        readFileSync(path, "utf8").includes(
          "werner_tobogganing_body_v2_transparent.png",
        ),
      );
      expect(importers.map((path) => path.slice(sourceRoot.length + 1))).toEqual([
        "brand/werner/WernerAuthoredPose.tsx",
      ]);
    });

    it("wrapper does NOT import or render canonical idle Werner", () => {
      const wrapper = readFileSync(
        "src/brand/werner/animated/WernerTobogganSpinner.tsx",
        "utf8",
      );
      // No import of the mascot Werner component (only WernerAuthoredPose is allowed)
      expect(wrapper).not.toMatch(
        /import Werner\b(?!AuthoredPose)/,
      );
      // No <Werner mood=… /> render
      expect(wrapper).not.toMatch(/<Werner\s/);
    });

    it("wrapper does NOT contain SVG sled slat geometry (rect/line elements)", () => {
      const wrapper = readFileSync(
        "src/brand/werner/animated/WernerTobogganSpinner.tsx",
        "utf8",
      );
      // No <rect> elements (the sled slat surface)
      expect(wrapper).not.toMatch(/<rect\s/);
    });
  });

  // ─── DOM structure (Acceptance gate 3) ──────────────────────────────
  describe("DOM structure", () => {
    it("renders exactly one role=status element", () => {
      const { container } = render(<WernerTobogganSpinner />);
      const statuses = container.querySelectorAll("[role=status]");
      expect(statuses).toHaveLength(1);
    });

    it("default aria-label is 'Loading…'", () => {
      const { container } = render(<WernerTobogganSpinner />);
      const status = container.querySelector("[role=status]");
      expect(status?.getAttribute("aria-label")).toBe("Loading…");
    });

    it("propagates custom label", () => {
      const { container } = render(
        <WernerTobogganSpinner label="Streaming investigation…" />,
      );
      const status = container.querySelector("[role=status]");
      expect(status?.getAttribute("aria-label")).toBe(
        "Streaming investigation…",
      );
    });

    it("renders exactly one authored body (data-werner-authored-pose=tobogganing)", () => {
      const { container } = render(<WernerTobogganSpinner />);
      const bodies = container.querySelectorAll(
        '[data-werner-authored-pose="tobogganing"]',
      );
      expect(bodies).toHaveLength(1);
      expect(bodies[0].tagName).toBe("IMG");
      expect(bodies[0].getAttribute("alt")).toBe("");
      expect(bodies[0].getAttribute("aria-hidden")).toBe("true");
      expect(bodies[0].getAttribute("draggable")).toBe("false");
    });

    it("renders exactly one decorative SVG speed-line layer", () => {
      const { container } = render(<WernerTobogganSpinner />);
      const svgs = container.querySelectorAll("svg[aria-hidden=true]");
      expect(svgs).toHaveLength(1);
      const speedlines = svgs[0].querySelectorAll(
        ".werner-toboggan-speedlines line",
      );
      expect(speedlines.length).toBeGreaterThan(0);
    });

    it("propagates caller size to wrapper width/height", () => {
      const { container } = render(<WernerTobogganSpinner size={64} />);
      const wrapper = container.querySelector("[role=status]");
      expect(wrapper?.getAttribute("style")).toContain("width: 64px");
      expect(wrapper?.getAttribute("style")).toContain("height: 64px");
    });

    it("propagates caller size to SVG", () => {
      const { container } = render(<WernerTobogganSpinner size={64} />);
      const svg = container.querySelector("svg");
      expect(svg?.getAttribute("width")).toBe("64");
      expect(svg?.getAttribute("height")).toBe("64");
    });

    it("propagates caller size to the authored body image", () => {
      const { container } = render(<WernerTobogganSpinner size={64} />);
      const body = container.querySelector(
        '[data-werner-authored-pose="tobogganing"]',
      );
      expect(body?.getAttribute("width")).toBe("64");
      expect(body?.getAttribute("height")).toBe("64");
    });

    it("no canonical idle Werner element exists in the DOM", () => {
      const { container } = render(<WernerTobogganSpinner />);
      // No data-werner-pose (Werner.tsx's img attribute) anywhere
      expect(container.querySelector("[data-werner-pose]")).toBeNull();
    });
  });

  // ─── Animation classes (Acceptance gate 4) ──────────────────────────
  describe("animation and reduced motion", () => {
    it("locks the established cadence and both reduced-motion paths", () => {
      const css = readFileSync(
        "src/brand/werner/animated/animations.css",
        "utf8",
      );
      expect(css).toMatch(
        /\.werner-toboggan\s*{[^}]*animation:\s*werner-toboggan-wobble 1200ms steps\(6, end\) infinite;/s,
      );
      expect(css).toMatch(
        /\.werner-toboggan-speedlines\s*{[^}]*animation:\s*werner-toboggan-speedlines 600ms ease-in-out infinite;/s,
      );
      expect(css).toMatch(
        /\.werner-toboggan-static \.werner-toboggan,\s*\.werner-toboggan-static \.werner-toboggan-speedlines\s*{[^}]*animation:\s*none;/s,
      );
      expect(css).toMatch(
        /@media \(prefers-reduced-motion: reduce\)\s*{[\s\S]*?\.werner-toboggan,[\s\S]*?\.werner-toboggan-speedlines,[\s\S]*?animation:\s*none !important;/,
      );
      for (const stop of ["0%", "16%", "33%", "50%", "66%", "83%", "100%"])
        expect(css).toContain(stop);
    });

    it("does not expand the four-mood public Werner contract", () => {
      const canonical = readFileSync("src/brand/Werner.tsx", "utf8");
      expect(canonical).toContain(
        'const MOODS = ["idle", "thinking", "empty", "celebrate"] as const;',
      );
      expect(canonical).not.toContain('"tobogganing"');
    });
    it("authored body carries the werner-toboggan wobble class", () => {
      const { container } = render(<WernerTobogganSpinner />);
      const body = container.querySelector(
        '[data-werner-authored-pose="tobogganing"]',
      );
      expect(body?.className).toContain("werner-toboggan");
    });

    it("speedlines group carries the flicker class", () => {
      const { container } = render(<WernerTobogganSpinner />);
      const lines = container.querySelector(".werner-toboggan-speedlines");
      expect(lines).not.toBeNull();
    });

    it("explicit reduced mode freezes the body and hides speed lines", () => {
      const { container } = render(<WernerTobogganSpinner reduced />);
      const status = container.querySelector("[role=status]");
      expect(status?.className).toContain("werner-toboggan-static");
      const lines = container.querySelector(
        ".werner-toboggan-speedlines",
      );
      expect(lines?.getAttribute("opacity")).toBe("0");
      expect(
        container.querySelectorAll(
          '[data-werner-authored-pose="tobogganing"]',
        ),
      ).toHaveLength(1);
    });

    it("no sled slat rendered in DOM (only speed lines and body)", () => {
      const { container } = render(<WernerTobogganSpinner />);
      const svgs = container.querySelectorAll("svg[aria-hidden=true]");
      expect(svgs).toHaveLength(1);
      // Only the speedlines <g> should exist inside the SVG, no toboggan-slat <g>
      const tobogganG = svgs[0].querySelectorAll(".werner-toboggan");
      // The .werner-toboggan class is on the WernerAuthoredPose img, not inside SVG
      expect(tobogganG).toHaveLength(0);
      // No <rect> inside the SVG (the old slat surface)
      expect(svgs[0].querySelectorAll("rect")).toHaveLength(0);
    });
  });
});
