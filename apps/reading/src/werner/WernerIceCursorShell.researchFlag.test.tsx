import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./iceFishingFlags", () => ({
  wernerIceFishingCursor: false,
}));

import { WernerIceCursorShell } from "./WernerIceCursorShell";

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  document.documentElement.classList.remove("werner-ice-cursor-hidden");
});

describe("research lens independence from the ice-fishing flag", () => {
  it("keeps research lens active when production disables ice fishing", () => {
    const { getByTestId } = render(
      <MemoryRouter initialEntries={["/inv/inv-production"]}>
        <WernerIceCursorShell />
      </MemoryRouter>,
    );
    expect(getByTestId("research-lens-cursor")).toBeTruthy();
    expect(document.documentElement.classList).toContain(
      "werner-ice-cursor-hidden",
    );
  });

  it("still disables bait and native-cursor hiding on an ice-fishing route", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/settings"]}>
        <WernerIceCursorShell />
      </MemoryRouter>,
    );
    expect(container.querySelector(".werner-ice-bait")).toBeNull();
    expect(document.documentElement.classList).not.toContain(
      "werner-ice-cursor-hidden",
    );
  });
});
