import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

import { LoadingGameHost } from "./LoadingGameHost";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
});

describe("LoadingGameHost mount contract", () => {
  it("hides when ready (does not block primary work)", () => {
    const { container } = render(
      <LoadingGameHost waiting ready game="zombies" arcadeEnabled />,
    );
    expect(container.querySelector('[data-testid="loading-game-host"]')).toBeNull();
  });

  it("shows plain loader before offer threshold", () => {
    render(
      <LoadingGameHost
        waiting
        ready={false}
        game="zombies"
        arcadeEnabled
        offerAfterMs={60_000}
      />,
    );
    const host = screen.getByTestId("loading-game-host");
    expect(host.getAttribute("data-host-mode")).toBe("plain-loader");
    expect(screen.getByTestId("loading-game-primary")).toBeTruthy();
  });

  it("primary control remains clickable while host is visible", () => {
    const onPrimary = vi.fn();
    render(
      <LoadingGameHost
        waiting
        ready={false}
        game="ice-fishing"
        arcadeEnabled
        offerAfterMs={60_000}
        onPrimaryContinue={onPrimary}
      />,
    );
    fireEvent.click(screen.getByTestId("loading-game-primary"));
    expect(onPrimary).toHaveBeenCalledTimes(1);
  });
});
