/**
 * livingTvAmbient.test.ts — pure policy + installer re-arm.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ambientExperienceAfterQuiet,
  DEFAULT_AMBIENT_QUIET_MS,
  installLivingTvAmbient,
} from "./livingTvAmbient";

afterEach(() => {
  vi.useRealTimers();
});

describe("ambientExperienceAfterQuiet", () => {
  it("stays silent before threshold", () => {
    expect(ambientExperienceAfterQuiet(0)).toBeNull();
    expect(ambientExperienceAfterQuiet(DEFAULT_AMBIENT_QUIET_MS - 1)).toBeNull();
  });

  it("returns idle at and after threshold", () => {
    expect(ambientExperienceAfterQuiet(DEFAULT_AMBIENT_QUIET_MS)).toBe("idle");
    expect(ambientExperienceAfterQuiet(DEFAULT_AMBIENT_QUIET_MS + 50_000)).toBe(
      "idle",
    );
  });

  it("rejects non-finite quiet", () => {
    expect(ambientExperienceAfterQuiet(Number.NaN)).toBeNull();
    expect(ambientExperienceAfterQuiet(-1)).toBeNull();
  });
});

describe("installLivingTvAmbient", () => {
  it("emits idle once after quiet, re-arms after product experience", () => {
    vi.useFakeTimers();
    const emit = vi.fn();
    const listeners = new Map<string, Set<EventListener>>();
    const target = {
      addEventListener: (type: string, fn: EventListener) => {
        if (!listeners.has(type)) listeners.set(type, new Set());
        listeners.get(type)!.add(fn);
      },
      removeEventListener: (type: string, fn: EventListener) => {
        listeners.get(type)?.delete(fn);
      },
    };
    let now = 0;
    const teardown = installLivingTvAmbient({
      quietMs: 1_000,
      pollMs: 200,
      emit,
      now: () => now,
      setInterval: (fn, ms) => window.setInterval(fn, ms) as unknown as number,
      clearInterval: (id) => window.clearInterval(id),
      target,
    });

    // Still quiet < threshold
    now = 500;
    vi.advanceTimersByTime(200);
    expect(emit).not.toHaveBeenCalled();

    // Cross threshold → one idle
    now = 1_100;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenCalledWith("idle");

    // Still quiet — not re-armed → no spam
    now = 5_000;
    vi.advanceTimersByTime(1_000);
    expect(emit).toHaveBeenCalledTimes(1);

    // Product experience re-arms
    for (const fn of listeners.get("antiek:werner-experience") ?? []) {
      fn(new Event("antiek:werner-experience"));
    }
    now = 5_000;
    // Advance past quiet again
    now = 6_200;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(2);

    teardown();
  });
});
