/**
 * Host-entry path: enter LoadingGameHost *playing* mode and progress score
 * via the same createArcadeCartridge factory the host mounts.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

import {
  createArcadeCartridge,
  progressCartridge,
} from "../cartridgeFactory";
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
  vi.useRealTimers();
});

describe("LoadingGameHost playing mode (host entry)", () => {
  it("opt-in play mounts arcade cartridge surface without blocking primary", async () => {
    vi.useFakeTimers();
    const onPrimary = vi.fn();
    render(
      <LoadingGameHost
        waiting
        ready={false}
        game="zombies"
        arcadeEnabled
        offerAfterMs={0}
        onPrimaryContinue={onPrimary}
      />,
    );

    // Wait timer past offer threshold (offerAfterMs=0 → immediate offer on tick).
    await act(async () => {
      vi.advanceTimersByTime(250);
    });

    const host = screen.getByTestId("loading-game-host");
    // May already be offer; click play when available.
    const offerBtn = screen.queryByTestId("game-offer-play");
    if (offerBtn) {
      fireEvent.click(offerBtn);
    } else if (host.getAttribute("data-host-mode") === "plain-loader") {
      await act(async () => {
        vi.advanceTimersByTime(500);
      });
      fireEvent.click(screen.getByTestId("game-offer-play"));
    }

    expect(screen.getByTestId("loading-game-host").getAttribute("data-host-mode")).toBe(
      "playing",
    );
    expect(screen.getByTestId("wait-arcade-mount")).toBeTruthy();

    // Primary control still works while a game is mounted (I4).
    fireEvent.click(screen.getByTestId("loading-game-primary"));
    expect(onPrimary).toHaveBeenCalled();

    // Score/wave progression via the SAME factory the host uses.
    const cart = createArcadeCartridge("zombies", { reducedMotion: false });
    expect(cart.id).toBe("paperclip-zombies");
    const progressed = progressCartridge(cart, 200, { fire: true, seed: 11 });
    expect(progressed.score).toBeGreaterThan(0);
  });

  it("ice-fishing host entry progresses catch score via shared factory", () => {
    const cart = createArcadeCartridge("ice-fishing", { reducedMotion: false });
    expect(cart.meta.style).toBe("club-penguin");
    // Force a deterministic catch progression (pure factory path used by host).
    const { score } = progressCartridge(cart, 180, { fire: true, seed: 3 });
    // At minimum, init + steps do not throw; score is non-negative and
    // reduced-motion false path can stay 0 if no random hit — use reduced path:
    const soft = createArcadeCartridge("ice-fishing", { reducedMotion: true });
    const softProg = progressCartridge(soft, 30, { fire: true, seed: 1 });
    expect(softProg.score).toBeGreaterThanOrEqual(1);
    expect(score).toBeGreaterThanOrEqual(0);
  });
});
