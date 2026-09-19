/**
 * ArcadeCabinet host-entry: click a game card → mount cartridge; progress
 * score via createArcadeCartridge (same factory the cabinet uses).
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ArcadeCabinet } from "./ArcadeCabinet";
import {
  createArcadeCartridge,
  progressCartridge,
} from "./cartridgeFactory";

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

afterEach(() => cleanup());

describe("ArcadeCabinet host entry", () => {
  it("renders session brand marks (celebrate + thinking) in the UI", () => {
    render(<ArcadeCabinet />);
    expect(screen.getByTestId("cabinet-brand-thinking")).toBeTruthy();
    expect(screen.getByTestId("cabinet-brand-celebrate")).toBeTruthy();
    // Must be real <img> sources (UI consumption, not inventory-only).
    const thinking = screen.getByTestId("cabinet-brand-thinking") as HTMLImageElement;
    const celebrate = screen.getByTestId(
      "cabinet-brand-celebrate",
    ) as HTMLImageElement;
    expect(thinking.getAttribute("src")).toBeTruthy();
    expect(celebrate.getAttribute("src")).toBeTruthy();
  });

  it("starts ice-fishing cartridge from cabinet click and progresses score via factory", () => {
    render(<ArcadeCabinet />);
    fireEvent.click(screen.getByTestId("cabinet-ice-fishing"));
    expect(screen.getByTestId("cabinet-play-surface")).toBeTruthy();
    expect(screen.getByTestId("cabinet-arcade-mount")).toBeTruthy();

    // Same factory ArcadeCabinet.useMemo calls.
    const cart = createArcadeCartridge("ice-fishing", { reducedMotion: true });
    expect(cart.id).toBe("ice-fishing");
    const { score } = progressCartridge(cart, 40, { fire: true, seed: 2 });
    expect(score).toBeGreaterThanOrEqual(1);
  });

  it("starts zombies cartridge from cabinet and progresses wave score", () => {
    render(<ArcadeCabinet />);
    fireEvent.click(screen.getByTestId("cabinet-zombies"));
    expect(screen.getByTestId("cabinet-arcade-mount")).toBeTruthy();

    const cart = createArcadeCartridge("zombies", { reducedMotion: false });
    expect(cart.id).toBe("paperclip-zombies");
    const { score } = progressCartridge(cart, 250, { fire: true, seed: 9 });
    expect(score).toBeGreaterThan(0);
  });
});
