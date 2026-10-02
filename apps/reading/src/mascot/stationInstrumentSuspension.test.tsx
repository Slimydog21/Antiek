import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  acquireStationInstrumentSuspension,
  isStationInstrumentSuspended,
  useStationInstrumentSuspended,
} from "./stationInstrumentSuspension";

function Observer() {
  return (
    <output data-testid="suspension">
      {useStationInstrumentSuspended() ? "suspended" : "route-owned"}
    </output>
  );
}

afterEach(cleanup);

describe("station instrument suspension", () => {
  it("holds overlapping leases until the final idempotent release", () => {
    render(<Observer />);
    expect(screen.getByTestId("suspension").textContent).toBe("route-owned");

    let releaseArcade = () => {};
    let releaseOverlay = () => {};
    act(() => {
      releaseArcade = acquireStationInstrumentSuspension("wait-arcade");
      releaseOverlay = acquireStationInstrumentSuspension("game-overlay");
    });
    expect(isStationInstrumentSuspended()).toBe(true);
    expect(screen.getByTestId("suspension").textContent).toBe("suspended");

    act(releaseArcade);
    expect(isStationInstrumentSuspended()).toBe(true);
    act(releaseOverlay);
    expect(isStationInstrumentSuspended()).toBe(false);
    expect(screen.getByTestId("suspension").textContent).toBe("route-owned");

    act(releaseOverlay);
    expect(isStationInstrumentSuspended()).toBe(false);
  });
});
