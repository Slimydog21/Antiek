import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

import {
  LoadingGameHost,
  waitHostBrandArt,
  waitHostOfferBlurb,
} from "./LoadingGameHost";

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

  it("renders game-specific session brand strip while host is visible", () => {
    render(
      <LoadingGameHost
        waiting
        ready={false}
        game="zombies"
        arcadeEnabled
        offerAfterMs={60_000}
      />,
    );
    const art = screen.getByTestId(
      "loading-game-living-tv-brand",
    ) as HTMLImageElement;
    expect(art.getAttribute("src") ?? "").toMatch(/werner_paperclip_zombies_arcade_session_v1/);
    expect(art.getAttribute("data-wait-game")).toBe("zombies");
    // Flipbook-feel invent reframe class densify (explicit, not only global CSS).
    expect(art.className).toMatch(/antiek-living-tv-invent/);
  });

  it("maps clam-catcher and ice-fishing wait-host brand art keys", () => {
    expect(waitHostBrandArt("clam-catcher")).toMatch(
      /werner_clam_catcher_cursor_session_v1/,
    );
    expect(waitHostBrandArt("ice-fishing")).toMatch(
      /werner_igloo_ice_arcade_cursor_session_v1/,
    );
    expect(waitHostBrandArt("zombies")).toMatch(/werner_paperclip_zombies_arcade_session_v1/);
    // Default invent is CRT living-TV (penguin as asynchronous TV show).
    expect(
      waitHostBrandArt("unknown" as Parameters<typeof waitHostBrandArt>[0]),
    ).toMatch(/werner_crt_igloo_cursor_tv_session_v1/);
  });

  it("offer blurbs name Club Penguin ice/clam and BO1 zombies egg", () => {
    expect(waitHostOfferBlurb("zombies")).toMatch(/Paperclip Zombies/i);
    expect(waitHostOfferBlurb("ice-fishing")).toMatch(/ice fishing/i);
    expect(waitHostOfferBlurb("clam-catcher")).toMatch(/clams/i);
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
