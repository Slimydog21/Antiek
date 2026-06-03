import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { WernerIceBait } from "./WernerIceBait";

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