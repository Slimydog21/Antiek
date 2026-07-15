import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../workspace/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: () => false,
}));

import { ArcadeCabinet } from "./ArcadeCabinet";

afterEach(() => cleanup());

describe("ArcadeCabinet host entry", () => {
  it("renders ice fishing and zombies cards", () => {
    render(<ArcadeCabinet />);
    expect(screen.getByTestId("cabinet-ice-fishing")).toBeTruthy();
    expect(screen.getByTestId("cabinet-zombies")).toBeTruthy();
  });

  it("renders session brand chrome marks (thinking + celebrate)", () => {
    render(<ArcadeCabinet />);
    expect(screen.getByTestId("cabinet-session-brand")).toBeTruthy();
    expect(screen.getByTestId("cabinet-brand-thinking")).toBeTruthy();
    expect(screen.getByTestId("cabinet-brand-celebrate")).toBeTruthy();
  });

  it("play mounts a game surface; close unmounts", () => {
    render(<ArcadeCabinet />);
    fireEvent.click(screen.getByTestId("cabinet-ice-fishing"));
    expect(screen.getByTestId("cabinet-play-surface")).toBeTruthy();
    fireEvent.click(screen.getByTestId("cabinet-close"));
    expect(screen.queryByTestId("cabinet-play-surface")).toBeNull();
  });

  it("starts zombies cartridge from cabinet and surfaces play mount", () => {
    // Host entry path: card click → createArcadeCartridge → ArcadeMount.
    render(<ArcadeCabinet />);
    fireEvent.click(screen.getByTestId("cabinet-zombies"));
    expect(screen.getByTestId("cabinet-play-surface")).toBeTruthy();
    expect(screen.getByTestId("cabinet-arcade-mount")).toBeTruthy();
  });
});
