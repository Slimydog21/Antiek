import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import WernerDuskGaze from "./WernerDuskGaze";

describe("WernerDuskGaze (SPR-29)", () => {
  it("uses the private authored pose without creating a product mood", () => {
    const { container } = render(<WernerDuskGaze size={64} />);
    expect(container.querySelector('[data-werner-dusk-gaze="true"]')).not.toBeNull();
    expect(container.querySelector('[data-werner-authored-pose="duskGaze"]')).not.toBeNull();
    expect(container.querySelector("[data-werner-mood]")).toBeNull();
  });

  it("collapses to a static wrapper for reduced motion", () => {
    const { container } = render(<WernerDuskGaze reduced />);
    const root = container.querySelector('[data-werner-dusk-gaze="true"]');
    expect(root?.getAttribute("data-reduced")).toBe("true");
    expect(root?.className).toBe("");
  });

  it("ships a real-alpha PNG rather than the generated checkerboard source", () => {
    const bytes = readFileSync(resolve("src/brand/werner/poses/werner_dusk_gaze_v1_transparent.png"));
    expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
    // PNG color type 6 at IHDR byte 25 means RGBA; RGB source type 2 is forbidden.
    expect(bytes[25]).toBe(6);
  });
});
