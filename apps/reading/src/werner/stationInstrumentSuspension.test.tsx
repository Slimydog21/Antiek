import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  acquireStationInstrumentSuspension,
  isStationInstrumentSuspended,
  stationInstrumentLeaseCount,
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
    expect(stationInstrumentLeaseCount()).toBe(2);
    expect(screen.getByTestId("suspension").textContent).toBe("suspended");

    act(releaseArcade);
    expect(isStationInstrumentSuspended()).toBe(true);
    expect(stationInstrumentLeaseCount()).toBe(1);
    act(releaseOverlay);
    expect(isStationInstrumentSuspended()).toBe(false);
    expect(stationInstrumentLeaseCount()).toBe(0);
    expect(screen.getByTestId("suspension").textContent).toBe("route-owned");

    act(releaseOverlay);
    expect(isStationInstrumentSuspended()).toBe(false);
  });

  it("wait-arcade densify suspends route instrument while the game owns the pointer", () => {
    // Fixed-station densify: focused wait-arcade returns pointer authority to
    // the product surface (cursor is instrument/bait, not a chase pet).
    expect(isStationInstrumentSuspended()).toBe(false);
    expect(stationInstrumentLeaseCount()).toBe(0);
    const release = acquireStationInstrumentSuspension("wait-arcade");
    expect(isStationInstrumentSuspended()).toBe(true);
    expect(stationInstrumentLeaseCount()).toBe(1);
    release();
    expect(isStationInstrumentSuspended()).toBe(false);
    expect(stationInstrumentLeaseCount()).toBe(0);
  });
});
