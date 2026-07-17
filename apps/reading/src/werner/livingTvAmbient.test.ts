/**
 * livingTvAmbient.test.ts — pure policy + installer re-arm + episode continuity.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ambientExperienceAfterQuiet,
  DEFAULT_AMBIENT_QUIET_MS,
  installLivingTvAmbient,
} from "./livingTvAmbient";
import { WERNER_EXPERIENCE_EVENT } from "./reactionBus";

afterEach(() => {
  vi.useRealTimers();
});

describe("ambientExperienceAfterQuiet", () => {
  it("stays silent before threshold", () => {
    expect(ambientExperienceAfterQuiet(0)).toBeNull();
    expect(ambientExperienceAfterQuiet(DEFAULT_AMBIENT_QUIET_MS - 1)).toBeNull();
  });

  it("returns idle at and after threshold (default episode)", () => {
    expect(ambientExperienceAfterQuiet(DEFAULT_AMBIENT_QUIET_MS)).toBe("idle");
    expect(ambientExperienceAfterQuiet(DEFAULT_AMBIENT_QUIET_MS + 50_000)).toBe(
      "idle",
    );
  });

  it("rejects non-finite quiet", () => {
    expect(ambientExperienceAfterQuiet(Number.NaN)).toBeNull();
    expect(ambientExperienceAfterQuiet(-1)).toBeNull();
  });

  it("continues deep_research_complete as soft note_saved savor", () => {
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "deep_research_complete",
      ),
    ).toBe("note_saved");
  });

  it("continues piece_started as soft note_saved savor", () => {
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "piece_started",
      ),
    ).toBe("note_saved");
  });

  it("sleeps after deep_research_start (research still running)", () => {
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "deep_research_start",
      ),
    ).toBe("idle");
  });

  it("does not re-loop ambient idle", () => {
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "idle",
      ),
    ).toBeNull();
  });

  it("continues arcade highlight episode as soft idle (no ambient spam)", () => {
    // Arcade / minigame door emits highlight; ambient TV show rests until next
    // product beat — cursor never auto-starts games.
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "highlight",
      ),
    ).toBe("idle");
  });

  it("recovers fail / deep_research_error episodes as soft idle densify", () => {
    // Living-TV densify: error beats recover with curtain idle, not pride loop.
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "fail",
      ),
    ).toBe("idle");
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "deep_research_error",
      ),
    ).toBe("idle");
    // After ambient idle, silence until a real product beat (no spam).
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "idle",
      ),
    ).toBeNull();
  });

  it("curtain-calls note_saved ambient into idle (sleep after pride)", () => {
    // After pride savor, the living-TV episode ends with sleep — not another
    // pride loop, and not silence without the curtain idle first.
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "note_saved",
      ),
    ).toBe("idle");
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

    // Product experience re-arms with a real episode (not bare Event — ambient
    // episode continuity needs the experience detail).
    for (const fn of listeners.get(WERNER_EXPERIENCE_EVENT) ?? []) {
      fn(
        new CustomEvent(WERNER_EXPERIENCE_EVENT, {
          detail: { experience: "highlight" },
        }),
      );
    }
    now = 5_000;
    // Advance past quiet again → idle continues the highlight episode
    now = 6_200;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(2);
    expect(emit).toHaveBeenLastCalledWith("idle");

    // Highlight ambient densify: idle does not re-arm — no ambient spam loop
    // until the next product beat (cursor never auto-starts games).
    now = 8_000;
    vi.advanceTimersByTime(1_000);
    expect(emit).toHaveBeenCalledTimes(2);

    teardown();
  });

  it("emits note_saved ambient after deep_research_complete episode", () => {
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

    // Product episode: research completed
    for (const fn of listeners.get(WERNER_EXPERIENCE_EVENT) ?? []) {
      fn(
        new CustomEvent(WERNER_EXPERIENCE_EVENT, {
          detail: { experience: "deep_research_complete" },
        }),
      );
    }
    now = 0;
    now = 1_100;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenCalledWith("note_saved");

    teardown();
  });

  it("curtain-calls deep_research_complete installer densify (pride → idle → silence)", () => {
    // Living-TV densify: complete research pride re-arms once for curtain idle.
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

    for (const fn of listeners.get(WERNER_EXPERIENCE_EVENT) ?? []) {
      fn(
        new CustomEvent(WERNER_EXPERIENCE_EVENT, {
          detail: { experience: "deep_research_complete" },
        }),
      );
    }
    now = 0;
    now = 1_100;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenLastCalledWith("note_saved");

    // Curtain densify: second quiet → idle sleep after pride.
    now = 2_200;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(2);
    expect(emit).toHaveBeenLastCalledWith("idle");

    // Silence densify: third quiet → no ambient spam.
    now = 5_000;
    vi.advanceTimersByTime(1_000);
    expect(emit).toHaveBeenCalledTimes(2);

    teardown();
  });

  it("curtain-calls pride savor into idle then silence (no ambient spam)", () => {
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

    // Product episode: piece started → ambient pride, then curtain idle.
    for (const fn of listeners.get(WERNER_EXPERIENCE_EVENT) ?? []) {
      fn(
        new CustomEvent(WERNER_EXPERIENCE_EVENT, {
          detail: { experience: "piece_started" },
        }),
      );
    }
    now = 0;
    now = 1_100;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenLastCalledWith("note_saved");

    // Second quiet window → curtain idle (sleep after pride).
    now = 2_200;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(2);
    expect(emit).toHaveBeenLastCalledWith("idle");

    // Third quiet window → silence (no ambient spam loop).
    now = 5_000;
    vi.advanceTimersByTime(1_000);
    expect(emit).toHaveBeenCalledTimes(2);

    teardown();
  });

  it("recovers deep_research_error installer densify with soft idle then silence", () => {
    // Living-TV densify: error beats re-arm quiet, emit recover idle, then silence.
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

    for (const fn of listeners.get(WERNER_EXPERIENCE_EVENT) ?? []) {
      fn(
        new CustomEvent(WERNER_EXPERIENCE_EVENT, {
          detail: { experience: "deep_research_error" },
        }),
      );
    }
    now = 0;
    now = 1_100;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenLastCalledWith("idle");

    // Idle does not re-arm — no ambient spam after error recover.
    now = 3_000;
    vi.advanceTimersByTime(1_000);
    expect(emit).toHaveBeenCalledTimes(1);

    teardown();
  });

  it("continues highlight installer densify with soft idle then silence", () => {
    // Living-TV densify: arcade highlight episode rests idle then silence
    // (cursor never auto-starts games; no ambient spam loop).
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

    for (const fn of listeners.get(WERNER_EXPERIENCE_EVENT) ?? []) {
      fn(
        new CustomEvent(WERNER_EXPERIENCE_EVENT, {
          detail: { experience: "highlight" },
        }),
      );
    }
    now = 0;
    now = 1_100;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenLastCalledWith("idle");

    // Idle densify: no re-arm after arcade highlight rest.
    now = 3_000;
    vi.advanceTimersByTime(1_000);
    expect(emit).toHaveBeenCalledTimes(1);

    teardown();
  });

  it("sleeps after deep_research_start installer densify (research still running)", () => {
    // Living-TV densify: while research runs, ambient sleeps idle then silence.
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

    for (const fn of listeners.get(WERNER_EXPERIENCE_EVENT) ?? []) {
      fn(
        new CustomEvent(WERNER_EXPERIENCE_EVENT, {
          detail: { experience: "deep_research_start" },
        }),
      );
    }
    now = 0;
    now = 1_100;
    vi.advanceTimersByTime(200);
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenLastCalledWith("idle");

    // Idle does not re-arm during research sleep densify.
    now = 3_000;
    vi.advanceTimersByTime(1_000);
    expect(emit).toHaveBeenCalledTimes(1);

    teardown();
  });
});

describe("livingTvAmbient Flipbook-feel honesty", () => {
  it("documents Flipbook-feel invent strips and pure Flipbook sole UI NO-GO", () => {
    const src = readFileSync(
      join(process.cwd(), "src/werner/livingTvAmbient.ts"),
      "utf8",
    );
    expect(src).toMatch(/Flipbook-feel invent strips/);
    expect(src).toMatch(/NO-GO/);
  });
});

