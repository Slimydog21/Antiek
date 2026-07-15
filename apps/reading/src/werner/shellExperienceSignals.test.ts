import { afterEach, describe, expect, it, vi } from "vitest";

import {
  consumeLocallyStartedResearchSession,
  notifyResearchPhaseEdge,
  notifyResearchStarted,
  notifyShellFailure,
  notifyModelEvidenceCompared,
  notifyOutlineBlockCommitted,
  notifySpeakInviteCommitted,
  notifySourceReadCommitted,
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

  it("maps a shell failure to one fail experience", () => {
    const capture = captureExperiences();
    notifyShellFailure();
    expect(capture.seen).toEqual(["fail"]);
    capture.teardown();
  });

  it("maps persisted reading evidence to one committed-source experience", () => {
    const capture = captureExperiences();
    notifySourceReadCommitted();
    expect(capture.seen).toEqual(["source_read_committed"]);
    capture.teardown();
  });

  it("maps a persisted outline block to one curious experience", () => {
    const capture = captureExperiences();
    notifyOutlineBlockCommitted();
    expect(capture.seen).toEqual(["outline_block_committed"]);
    capture.teardown();
  });

  it("maps a committed Speak invitation to one happy experience", () => {
    const capture = captureExperiences();
    notifySpeakInviteCommitted();
    expect(capture.seen).toEqual(["speak_invite_committed"]);
    capture.teardown();
  });

  it("maps a completed model evidence comparison to one curious experience", () => {
    const capture = captureExperiences();
    notifyModelEvidenceCompared();
    expect(capture.seen).toEqual(["model_evidence_compared"]);
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
