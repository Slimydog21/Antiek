import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("./PriceCeilingPanel", () => ({
  default: function StubPriceCeilingPanel() {
    return <div data-testid="price-ceiling-panel">price-ceiling-stub</div>;
  },
}));

import MidnightOilMode from "./index";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("MidnightOilMode", () => {
  it("renders mode shell and mounts PriceCeilingPanel", () => {
    render(<MidnightOilMode />);
    expect(screen.getByTestId("midnight-oil-mode")).toBeTruthy();
    expect(screen.getByTestId("midnight-oil-header").textContent).toMatch(
      /Midnight Oil/i,
    );
    expect(screen.getByTestId("midnight-oil-ceiling-slot")).toBeTruthy();
    expect(screen.getByTestId("price-ceiling-panel").textContent).toMatch(
      /price-ceiling-stub/,
    );
  });

  it("states advisory ceiling does not spend until approve", () => {
    render(<MidnightOilMode />);
    expect(screen.getByTestId("midnight-oil-blurb").textContent).toMatch(
      /never spend|approve/i,
    );
  });
});
