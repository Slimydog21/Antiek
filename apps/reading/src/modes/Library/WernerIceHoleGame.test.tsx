import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { arcadeProps, loadBackdrop, reducedMotion } = vi.hoisted(() => ({
  arcadeProps: vi.fn(),
  loadBackdrop: vi.fn(),
  reducedMotion: { current: false },
}));

vi.mock("../../arcade/engine/ArcadeMount", () => ({
  ArcadeMount: (props: unknown) => {
    arcadeProps(props);
    return <canvas data-testid="game-canvas" />;
  },
}));
vi.mock("../../arcade/games/ice-fishing/iceFishingBackdrop", () => ({
  loadIceFishingBackdrop: (...args: unknown[]) => loadBackdrop(...args),
}));
vi.mock("../../workspace/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: () => reducedMotion.current,
}));

import WernerIceHoleGame from "./WernerIceHoleGame";

afterEach(() => {
  cleanup();
  arcadeProps.mockReset();
  loadBackdrop.mockReset();
  reducedMotion.current = false;
});

describe("WernerIceHoleGame", () => {
  it("loads the authored plate and repaints the existing cartridge on readiness", () => {
    loadBackdrop.mockImplementation(
      (
        _url: string,
        _target: unknown,
        _factory: unknown,
        onReady: () => void,
      ) => {
        onReady();
        return vi.fn();
      },
    );
    render(<WernerIceHoleGame />);
    expect(screen.getByTestId("game-canvas")).toBeTruthy();
    expect(loadBackdrop).toHaveBeenCalledOnce();
    const first = arcadeProps.mock.calls[0]?.[0] as { redrawToken: number };
    const last = arcadeProps.mock.calls.at(-1)?.[0] as {
      redrawToken: number;
      reducedMotion: boolean;
    };
    expect(first.redrawToken).toBe(0);
    expect(last.redrawToken).toBe(1);
    expect(last.reducedMotion).toBe(false);
  });

  it("publishes discrete encounter instructions under reduced motion", () => {
    reducedMotion.current = true;
    loadBackdrop.mockReturnValue(vi.fn());
    render(<WernerIceHoleGame />);
    const props = arcadeProps.mock.calls.at(-1)?.[0] as {
      reducedMotion: boolean;
      instructions: string;
    };
    expect(props.reducedMotion).toBe(true);
    expect(props.instructions).toMatch(/still fish-or-boot encounter/);
  });
});
