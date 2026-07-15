import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import WernerWaking from "./WernerWaking";

describe("WernerWaking authored ownership", () => {
  it("renders one decorative centrally mapped waking pose", () => {
    const { container } = render(<WernerWaking size={64} />);
    expect(
      container.querySelectorAll('[data-werner-authored-pose="waking"]'),
    ).toHaveLength(1);
    expect(container.querySelector("[role=img]")).toBeNull();
  });

  it("keeps the raster import in WernerAuthoredPose, never the wrapper or mascot", () => {
    const map = readFileSync("src/brand/werner/WernerAuthoredPose.tsx", "utf8");
    const wrapper = readFileSync(
      "src/brand/werner/animated/WernerWaking.tsx",
      "utf8",
    );
    const mascot = readFileSync("src/shell/PenguinMascot.tsx", "utf8");
    expect(map).toContain("werner_waking_v1_transparent.png");
    expect(wrapper).not.toMatch(/poses\/werner_waking/);
    expect(mascot).not.toMatch(/poses\/werner_waking/);
    expect(map).not.toContain("werner_waking_v1_chroma.png");
  });
});
