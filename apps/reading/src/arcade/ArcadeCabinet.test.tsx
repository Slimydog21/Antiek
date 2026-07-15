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

  it("play mounts a game surface; close unmounts", () => {
    render(<ArcadeCabinet />);
    fireEvent.click(screen.getByTestId("cabinet-ice-fishing"));
    expect(screen.getByTestId("cabinet-play-surface")).toBeTruthy();
    fireEvent.click(screen.getByTestId("cabinet-close"));
    expect(screen.queryByTestId("cabinet-play-surface")).toBeNull();
  });
});
