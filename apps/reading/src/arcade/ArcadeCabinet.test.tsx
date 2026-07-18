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
import { WERNER_EXPERIENCE_EVENT } from "../werner/reactionBus";

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
    expect(screen.getByTestId("cabinet-session-brand")).toBeTruthy();
    expect(screen.getByTestId("cabinet-brand-thinking")).toBeTruthy();
    expect(screen.getByTestId("cabinet-brand-celebrate")).toBeTruthy();
    const thinking = screen.getByTestId(
      "cabinet-brand-thinking",
    ) as HTMLImageElement;
    const celebrate = screen.getByTestId(
      "cabinet-brand-celebrate",
    ) as HTMLImageElement;
    expect(thinking.getAttribute("src")).toBeTruthy();
    expect(celebrate.getAttribute("src")).toBeTruthy();
  });

  it("renders igloo arcade session invent banner in cabinet chrome", () => {
    render(<ArcadeCabinet />);
    const art = screen.getByTestId("cabinet-igloo-art") as HTMLImageElement;
    expect(art.getAttribute("src") ?? "").toMatch(
      /werner_igloo_minigame_trio_session_v1/,
    );
    expect(art.className).toMatch(/antiek-living-tv-invent/);
  });

  it("stamps Flipbook invent reframe on minigame card invent art", () => {
    render(<ArcadeCabinet />);
    for (const id of [
      "cabinet-ice-fishing",
      "cabinet-clam-catcher",
      "cabinet-zombies",
    ] as const) {
      const art = screen.getByTestId(`${id}-living-tv-art`) as HTMLImageElement;
      expect(art.className).toMatch(/antiek-living-tv-invent/);
      expect(art.getAttribute("src")).toBeTruthy();
    }
  });

  it("renders ice fishing, clam catcher, and zombies cards", () => {
    render(<ArcadeCabinet />);
    expect(screen.getByTestId("cabinet-ice-fishing")).toBeTruthy();
    expect(screen.getByTestId("cabinet-clam-catcher")).toBeTruthy();
    expect(screen.getByTestId("cabinet-zombies")).toBeTruthy();
    // Living-TV geometry: per-game product doors so penguin choreography
    // resolves ice-fishing / clam-catcher / zombies → curious.
    expect(
      screen.getByTestId("cabinet-ice-fishing").getAttribute("data-product-id"),
    ).toBe("ice-fishing");
    expect(
      screen.getByTestId("cabinet-clam-catcher").getAttribute("data-product-id"),
    ).toBe("clam-catcher");
    expect(
      screen.getByTestId("cabinet-zombies").getAttribute("data-product-id"),
    ).toBe("zombies");
  });

  it("starts clam-catcher cartridge from cabinet click via shared factory", () => {
    render(<ArcadeCabinet />);
    fireEvent.click(screen.getByTestId("cabinet-clam-catcher"));
    expect(screen.getByTestId("cabinet-play-surface")).toBeTruthy();
    expect(screen.getByTestId("cabinet-arcade-mount")).toBeTruthy();
    const cart = createArcadeCartridge("clam-catcher", { reducedMotion: true });
    expect(cart.id).toBe("clam-catcher");
    const { score } = progressCartridge(cart, 40, { fire: true, seed: 4 });
    expect(score).toBeGreaterThanOrEqual(0);
  });

  it("starts ice-fishing cartridge from cabinet click and progresses score via factory", () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    render(<ArcadeCabinet />);
    fireEvent.click(screen.getByTestId("cabinet-ice-fishing"));
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    expect(screen.getByTestId("cabinet-play-surface")).toBeTruthy();
    expect(screen.getByTestId("cabinet-arcade-mount")).toBeTruthy();
    expect(seen).toContain("highlight");

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

  it("play mounts a game surface; close unmounts", () => {
    render(<ArcadeCabinet />);
    fireEvent.click(screen.getByTestId("cabinet-ice-fishing"));
    expect(screen.getByTestId("cabinet-play-surface")).toBeTruthy();
    fireEvent.click(screen.getByTestId("cabinet-close"));
    expect(screen.queryByTestId("cabinet-play-surface")).toBeNull();
  });
});
