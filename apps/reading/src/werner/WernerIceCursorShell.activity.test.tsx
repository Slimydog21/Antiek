import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

describe("Werner cursor shell activity selection", () => {
  it("mounts the research lens on a knowledge-work route", () => {
    const { getByTestId, unmount } = render(
      <MemoryRouter initialEntries={["/deep-research/session-8"]}>
        <WernerIceCursorShell />
      </MemoryRouter>,
    );
    expect(getByTestId("research-lens-cursor")).toBeTruthy();
    expect(document.documentElement.classList).toContain(
      "werner-ice-cursor-hidden",
    );
    unmount();
    expect(document.documentElement.classList).not.toContain(
      "werner-ice-cursor-hidden",
    );
  });

  it("keeps ice fishing on a utility route", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/settings"]}>
        <WernerIceCursorShell />
      </MemoryRouter>,
    );
    expect(container.querySelector(".werner-ice-bait")).toBeTruthy();
    expect(container.querySelector(".research-lens-cursor")).toBeNull();
  });
});
