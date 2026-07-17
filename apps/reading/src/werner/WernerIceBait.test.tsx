import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { baitChromeFromFollow, WernerIceBait } from "./WernerIceBait";

describe("baitChromeFromFollow instrument densify", () => {
  it("pins chrome to live pointer (cursor IS bait — not lag chase)", () => {
    expect(
      baitChromeFromFollow({ live: { x: 120, y: 80 }, tabHidden: false }),
    ).toEqual({ display: "block", left: "120px", top: "80px" });
  });

  it("hides when there is no live pointer or the tab is hidden", () => {
    expect(baitChromeFromFollow({ live: null, tabHidden: false })).toEqual({
      display: "none",
    });
    expect(
      baitChromeFromFollow({ live: { x: 1, y: 2 }, tabHidden: true }),
    ).toEqual({ display: "none" });
  });
});

describe("WernerIceBait", () => {
  it("renders bait chrome when enabled", () => {
    const { container } = render(<WernerIceBait />);
    expect(container.querySelector(".werner-ice-bait")).toBeTruthy();
  });

  it("renders nothing when disabled (reduced motion path)", () => {
    const { container } = render(<WernerIceBait disabled />);
    expect(container.querySelector(".werner-ice-bait")).toBeNull();
  });
});
