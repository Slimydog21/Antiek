import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createStationRestLifecycle,
  STATION_LONG_REST_MS,
  STATION_WAKE_MS,
  type StationRestPhase,
} from "./stationRestLifecycle";

describe("station long-rest lifecycle", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("keeps two-second activity idle distinct from long rest", () => {
    const phases: StationRestPhase[] = [];
    const lifecycle = createStationRestLifecycle((phase) => phases.push(phase));
    lifecycle.setEligible(true);
    vi.advanceTimersByTime(2_600);
    expect(lifecycle.getPhase()).toBe("active");
    expect(phases).toEqual(["active"]);
    vi.advanceTimersByTime(STATION_LONG_REST_MS - 2_600);
    expect(lifecycle.getPhase()).toBe("sleeping");
  });

  it("wakes exactly once and does not extend waking on repeated input", () => {
    const phases: StationRestPhase[] = [];
    const lifecycle = createStationRestLifecycle((phase) => phases.push(phase));
    lifecycle.setEligible(true);
    vi.advanceTimersByTime(STATION_LONG_REST_MS);
    lifecycle.noteInteraction();
    vi.advanceTimersByTime(STATION_WAKE_MS - 1);
    lifecycle.noteInteraction();
    vi.advanceTimersByTime(1);
    expect(lifecycle.getPhase()).toBe("active");
    expect(phases).toEqual(["active", "sleeping", "waking", "active"]);
  });

  it("invalidates stale deadlines on preemption and starts a fresh epoch", () => {
    const lifecycle = createStationRestLifecycle(() => {});
    lifecycle.setEligible(true);
    vi.advanceTimersByTime(STATION_LONG_REST_MS - 1);
    lifecycle.setEligible(false);
    expect(lifecycle.getPhase()).toBe("suspended");
    vi.advanceTimersByTime(10_000);
    lifecycle.setEligible(true);
    vi.advanceTimersByTime(STATION_LONG_REST_MS - 1);
    expect(lifecycle.getPhase()).toBe("active");
    vi.advanceTimersByTime(1);
    expect(lifecycle.getPhase()).toBe("sleeping");
  });

  it("rejects manually delivered stale rest and wake callbacks", () => {
    const callbacks = new Map<number, () => void>();
    let nextId = 0;
    const scheduler = {
      setTimeout(fn: () => void) {
        const id = ++nextId;
        callbacks.set(id, fn);
        return id;
      },
      // Hostile scheduler: cancellation is deliberately ineffective, modeling
      // a callback already queued at the event-loop boundary.
      clearTimeout() {},
    };
    const lifecycle = createStationRestLifecycle(() => {}, {
      restMs: 10,
      wakeMs: 5,
      scheduler,
    });
    lifecycle.setEligible(true);
    const staleRest = callbacks.get(1)!;
    lifecycle.setEligible(false);
    staleRest();
    expect(lifecycle.getPhase()).toBe("suspended");

    lifecycle.setEligible(true);
    callbacks.get(2)!();
    expect(lifecycle.getPhase()).toBe("sleeping");
    lifecycle.noteInteraction();
    const staleWake = callbacks.get(3)!;
    lifecycle.setEligible(false);
    staleWake();
    expect(lifecycle.getPhase()).toBe("suspended");
  });

  it("does not wake from suspension or visibility-style eligibility return", () => {
    const phases: StationRestPhase[] = [];
    const lifecycle = createStationRestLifecycle((phase) => phases.push(phase));
    lifecycle.noteInteraction();
    lifecycle.setEligible(true);
    expect(phases).toEqual(["active"]);
    expect(phases).not.toContain("waking");
  });

  it("clears all pending work on dispose", () => {
    const lifecycle = createStationRestLifecycle(() => {});
    lifecycle.setEligible(true);
    lifecycle.dispose();
    vi.advanceTimersByTime(STATION_LONG_REST_MS + STATION_WAKE_MS);
    expect(lifecycle.getPhase()).toBe("suspended");
    expect(vi.getTimerCount()).toBe(0);
  });
});
