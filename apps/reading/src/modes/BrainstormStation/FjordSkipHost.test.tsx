import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const gameMount = vi.hoisted(() => vi.fn());

vi.mock("./FjordSkipGame", () => ({
  default: () => {
    gameMount();
    return (
      <canvas data-testid="fjord-skip-canvas" role="application" tabIndex={0} />
    );
  },
}));

import { isStationInstrumentSuspended } from "../../werner/stationInstrumentSuspension";
import FjordSkipHost from "./FjordSkipHost";

beforeEach(() => gameMount.mockReset());
afterEach(() => cleanup());

describe("FjordSkipHost", () => {
  it("keeps game code unmounted until explicit Play", () => {
    render(<FjordSkipHost />);
    expect(screen.getByText("Fjord Skip")).toBeTruthy();
    expect(gameMount).not.toHaveBeenCalled();
    expect(screen.queryByTestId("fjord-skip-canvas")).toBeNull();
  });

  it("suspends the station instrument only during play", async () => {
    render(<FjordSkipHost />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play Fjord Skip" }));
    });
    expect(gameMount).toHaveBeenCalledOnce();
    expect(isStationInstrumentSuspended()).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Exit game" }));
    expect(isStationInstrumentSuspended()).toBe(false);
  });

  it.each(["Escape", "button"])(
    "exits with %s and restores focus",
    async (kind) => {
      render(<FjordSkipHost />);
      fireEvent.click(screen.getByRole("button", { name: "Play Fjord Skip" }));
      await screen.findByTestId("fjord-skip-canvas");
      if (kind === "Escape") {
        fireEvent.keyDown(screen.getByTestId("fjord-skip-canvas"), {
          key: "Escape",
        });
      } else {
        fireEvent.click(screen.getByRole("button", { name: "Exit game" }));
      }
      const play = screen.getByRole("button", { name: "Play Fjord Skip" });
      expect(play).toBe(document.activeElement);
      expect(screen.queryByTestId("fjord-skip-canvas")).toBeNull();
    },
  );

  it("announces itself as a thinking break, not research", () => {
    render(<FjordSkipHost />);
    expect(
      screen.getAllByText(/thinking break/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/thinking break, nothing more/i)).toBeTruthy();
  });
});
