import { afterEach, describe, expect, it, vi } from "vitest";

import {
  consumeLocallyStartedResearchSession,
  notifyPointerIdleEdge,
  notifyResearchPhaseEdge,
  notifyResearchStarted,
  notifyShellFailure,
} from "./shellExperienceSignals";
import {
  WERNER_EXPERIENCE_EVENT,
  type ProductExperience,
} from "./reactionBus";

function captureExperiences(): {
  seen: ProductExperience[];
  teardown: () => void;
} {
  const seen: ProductExperience[] = [];
  const listener = (event: Event) => {
    const experience = (event as CustomEvent).detail?.experience;
    if (experience) seen.push(experience);
  };
  window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
  return {
    seen,
    teardown: () =>
      window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener),
  };
}

describe("Werner shell experience edges", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("emits idle only on the false to true edge", () => {
    const capture = captureExperiences();
    expect(notifyPointerIdleEdge(false, false)).toBe(false);
    expect(notifyPointerIdleEdge(false, true)).toBe(true);
    expect(notifyPointerIdleEdge(true, true)).toBe(false);
    expect(notifyPointerIdleEdge(true, false)).toBe(false);
    expect(capture.seen).toEqual(["idle"]);
    capture.teardown();
  });

  it("does not turn an eligibility gate reopening into a pointer-idle edge", () => {
    const capture = captureExperiences();
    expect(notifyPointerIdleEdge(false, true, false)).toBe(false);
    // The real pointer edge happened while hidden/dragging. Reopening that gate
    // leaves pointer state idle→idle and therefore stays silent.
    expect(notifyPointerIdleEdge(true, true, true)).toBe(false);
    expect(capture.seen).toEqual([]);
    capture.teardown();
  });

  it("maps a shell failure to one fail experience", () => {
    const capture = captureExperiences();
    notifyShellFailure();
    expect(capture.seen).toEqual(["fail"]);
    capture.teardown();
  });

  it("emits research start only from the successful launch boundary", () => {
    const capture = captureExperiences();
    notifyResearchStarted("session-signal-test");
    expect(capture.seen).toEqual(["deep_research_start"]);
    expect(consumeLocallyStartedResearchSession("session-signal-test")).toBe(true);
    expect(consumeLocallyStartedResearchSession("session-signal-test")).toBe(false);
    capture.teardown();
  });

  it("expires launch provenance when navigation never mounts a monitor", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000);
    notifyResearchStarted("session-abandoned-navigation");
    vi.advanceTimersByTime(10_001);
    expect(
      consumeLocallyStartedResearchSession("session-abandoned-navigation"),
    ).toBe(false);
  });

  it("emits terminal lifecycle transitions but never replays launch from polling", () => {
    const capture = captureExperiences();
    expect(notifyResearchPhaseEdge("idle", "running")).toBe(false);
    expect(notifyResearchPhaseEdge("running", "running")).toBe(false);
    expect(notifyResearchPhaseEdge("running", "error")).toBe(true);
    expect(notifyResearchPhaseEdge("error", "error")).toBe(false);
    expect(notifyResearchPhaseEdge("error", "running")).toBe(false);
    expect(notifyResearchPhaseEdge("running", "complete")).toBe(true);
    expect(notifyResearchPhaseEdge("complete", "complete")).toBe(false);
    expect(notifyResearchPhaseEdge("complete", "idle")).toBe(false);
    expect(capture.seen).toEqual([
      "deep_research_error",
      "deep_research_complete",
    ]);
    capture.teardown();
  });
});
