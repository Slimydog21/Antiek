import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const gameMount = vi.hoisted(() => vi.fn());

vi.mock("./WernerIceHoleGame", () => ({
  default: () => {
    gameMount();
    return (
      <canvas
        data-testid="werner-ice-hole-canvas"
        role="application"
        tabIndex={0}
      />
    );
  },
}));

import { isStationInstrumentSuspended } from "../../werner/stationInstrumentSuspension";
import WernerIceHole from "./WernerIceHole";

beforeEach(() => gameMount.mockReset());
afterEach(() => cleanup());

describe("WernerIceHole", () => {
  it("keeps game code unmounted until explicit Play", () => {
    render(<WernerIceHole />);
    expect(screen.getByText("Visit the ice hole")).toBeTruthy();
    expect(gameMount).not.toHaveBeenCalled();
    expect(screen.queryByTestId("werner-ice-hole-canvas")).toBeNull();
  });

  it("suspends the station instrument only during play", async () => {
    render(<WernerIceHole />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play Ice Fishing" }));
    });
    expect(gameMount).toHaveBeenCalledOnce();
    expect(isStationInstrumentSuspended()).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Exit game" }));
    expect(isStationInstrumentSuspended()).toBe(false);
  });

  it.each(["Escape", "button"])(
    "exits with %s and restores focus",
    async (kind) => {
      render(<WernerIceHole />);
      fireEvent.click(screen.getByRole("button", { name: "Play Ice Fishing" }));
      await screen.findByTestId("werner-ice-hole-canvas");
      if (kind === "Escape") {
        fireEvent.keyDown(screen.getByTestId("werner-ice-hole-canvas"), {
          key: "Escape",
        });
      } else {
        fireEvent.click(screen.getByRole("button", { name: "Exit game" }));
      }
      const play = screen.getByRole("button", { name: "Play Ice Fishing" });
      expect(play).toBe(document.activeElement);
      expect(screen.queryByTestId("werner-ice-hole-canvas")).toBeNull();
    },
  );
});
