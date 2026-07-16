import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./ResearchWaitArcade.css";
import { emitLivingTvHostBeat } from "../../arcade/host/livingTvHostEmit";
import { LIVING_TV_HOST_EVENT } from "../../arcade/host/livingTvHostEmit";

const createArcadeCartridge = vi.hoisted(() => vi.fn(() => ({ id: "test" })));

vi.mock("../../arcade/cartridgeFactory", () => ({
  createArcadeCartridge,
}));

vi.mock("../../arcade/engine/ArcadeMount", () => ({
  ArcadeMount: () => (
    <canvas
      data-testid="research-wait-arcade-canvas"
      role="application"
      tabIndex={0}
    />
  ),
}));

import ResearchWaitArcadeGame from "./ResearchWaitArcadeGame";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  createArcadeCartridge.mockClear();
});

describe("ResearchWaitArcadeGame authored cabinet", () => {
  it("keeps one decorative scene layer behind the sole interactive canvas", () => {
    const { container } = render(
      <ResearchWaitArcadeGame
        game="ice-fishing"
        reducedMotion={false}
        sceneArtSrc="/authored/ice-fishing.webp"
      />,
    );

    const cabinet = container.querySelector(
      ".research-wait-arcade__cabinet",
    ) as HTMLDivElement;
    const scene = cabinet.querySelector("img") as HTMLImageElement;
    const applications = screen.getAllByRole("application");

    expect(scene.src).toContain("/authored/ice-fishing.webp");
    expect(scene.alt).toBe("");
    expect(scene.getAttribute("aria-hidden")).toBe("true");
    expect(scene.getAttribute("decoding")).toBe("async");
    expect(scene.tabIndex).toBe(-1);
    expect(scene.style.pointerEvents).toBe("none");
    expect(scene.draggable).toBe(false);
    expect(cabinet.className).toBe("research-wait-arcade__cabinet");
    expect(applications).toHaveLength(1);
    expect(applications[0]).toBe(document.activeElement);
  });

  it("injects emitLivingTvHostBeat so in-game beats reach living-TV (not no-op)", () => {
    render(
      <ResearchWaitArcadeGame
        game="zombies"
        reducedMotion={false}
        sceneArtSrc="/authored/zombies.webp"
      />,
    );

    expect(createArcadeCartridge).toHaveBeenCalledWith("zombies", {
      reducedMotion: false,
      onWernerBeat: emitLivingTvHostBeat,
    });

    // Drive the shipped host emit path: beat must dispatch the living-TV event.
    const opts = createArcadeCartridge.mock.calls[0]?.[1] as {
      onWernerBeat?: (beat: string) => void;
    };
    expect(opts.onWernerBeat).toBe(emitLivingTvHostBeat);

    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent<{ experience?: string }>).detail?.experience;
      if (d) seen.push(d);
    };
    window.addEventListener(LIVING_TV_HOST_EVENT, onExp);
    opts.onWernerBeat?.("highlight");
    opts.onWernerBeat?.("piece_started");
    opts.onWernerBeat?.("fail");
    window.removeEventListener(LIVING_TV_HOST_EVENT, onExp);

    expect(seen).toEqual(["highlight", "piece_started", "fail"]);
  });
});
