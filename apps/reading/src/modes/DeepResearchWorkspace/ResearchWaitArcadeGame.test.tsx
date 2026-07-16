import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./ResearchWaitArcade.css";

const createArcadeCartridge = vi.hoisted(() => vi.fn(() => ({ id: "test" })));
const mountProps = vi.hoisted(() => vi.fn());

vi.mock("../../arcade/cartridgeFactory", () => ({
  createArcadeCartridge,
}));

vi.mock("../../arcade/engine/ArcadeMount", () => ({
  ArcadeMount: (props: { paused?: boolean }) => {
    mountProps(props);
    return (
      <canvas
        data-testid="research-wait-arcade-canvas"
        role="application"
        tabIndex={0}
      />
    );
  },
}));

import ResearchWaitArcadeGame from "./ResearchWaitArcadeGame";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
    expect(createArcadeCartridge).toHaveBeenCalledWith("ice-fishing", {
      reducedMotion: false,
    });
    expect(mountProps).toHaveBeenLastCalledWith(
      expect.objectContaining({ paused: false }),
    );
  });

  it("forwards broadcast pause without recreating the cartridge", () => {
    const callsBefore = createArcadeCartridge.mock.calls.length;
    const view = render(
      <ResearchWaitArcadeGame
        game="zombies"
        reducedMotion={false}
        sceneArtSrc="/authored/zombies.webp"
      />,
    );
    view.rerender(
      <ResearchWaitArcadeGame
        game="zombies"
        reducedMotion={false}
        sceneArtSrc="/authored/zombies.webp"
        paused
      />,
    );
    expect(createArcadeCartridge).toHaveBeenCalledTimes(callsBefore + 1);
    expect(mountProps).toHaveBeenLastCalledWith(
      expect.objectContaining({ paused: true }),
    );
  });
});
