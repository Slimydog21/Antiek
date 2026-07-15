import { act, cleanup, render } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  notifyResearchStarted,
  WERNER_EXPERIENCE_EVENT,
} from "../../werner";
import {
  deriveResearchReactionPhase,
  useWernerResearchReactions,
  type ResearchReactionSnapshot,
} from "./useWernerResearchReactions";

function Host({ snapshot }: { snapshot: ResearchReactionSnapshot }) {
  useWernerResearchReactions(snapshot);
  return null;
}

const IDLE: ResearchReactionSnapshot = {
  sessionId: "session-1",
  loading: false,
  allTerminal: false,
  error: null,
  researchStates: [],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Werner deep-research reactions", () => {
  it("derives only authoritative success and failure outcomes", () => {
    expect(deriveResearchReactionPhase(IDLE)).toBe("idle");
    expect(deriveResearchReactionPhase({ ...IDLE, researchStates: ["running"] })).toBe("running");
    expect(deriveResearchReactionPhase({ ...IDLE, allTerminal: true, researchStates: ["done", "done"] })).toBe("complete");
    expect(deriveResearchReactionPhase({ ...IDLE, allTerminal: true, researchStates: ["done", "failed"] })).toBe("error");
    expect(deriveResearchReactionPhase({ ...IDLE, allTerminal: true, researchStates: ["budget_halted"] })).toBe("error");
    expect(deriveResearchReactionPhase({ ...IDLE, researchStates: ["failed", "running"] })).toBe("error");
    expect(deriveResearchReactionPhase({ ...IDLE, allTerminal: true, researchStates: ["stopped"] })).toBe("idle");
    expect(deriveResearchReactionPhase({ ...IDLE, error: "offline" })).toBe("error");
  });

  it("emits terminal edges once while polling and recovery stay silent", () => {
    const experiences: string[] = [];
    const listener = (event: Event) => {
      experiences.push((event as CustomEvent).detail.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
    const view = render(<Host snapshot={IDLE} />);

    const running = { ...IDLE, researchStates: ["running"] as const };
    act(() => view.rerender(<Host snapshot={running} />));
    act(() => view.rerender(<Host snapshot={{ ...running }} />));
    act(() => view.rerender(<Host snapshot={{ ...IDLE, error: "offline" }} />));
    act(() => view.rerender(<Host snapshot={{ ...IDLE, error: "offline" }} />));
    act(() => view.rerender(<Host snapshot={{ ...IDLE, researchStates: ["running"] }} />));
    act(() => view.rerender(<Host snapshot={{ ...IDLE, allTerminal: true, researchStates: ["done", "done"] }} />));

    expect(experiences).toEqual([
      "deep_research_error",
      "deep_research_complete",
    ]);
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });

  it("baselines initial and changed sessions without replaying history", () => {
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
    const complete = {
      ...IDLE,
      allTerminal: true,
      researchStates: ["done"] as const,
    };
    const view = render(
      <StrictMode>
        <Host snapshot={complete} />
      </StrictMode>,
    );
    expect(listener).not.toHaveBeenCalled();

    act(() =>
      view.rerender(
        <StrictMode>
          <Host snapshot={{ ...complete, sessionId: "session-2" }} />
        </StrictMode>,
      ),
    );
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });

  it("ignores loading history but reacts to a locally launched first outcome", () => {
    const experiences: string[] = [];
    const listener = (event: Event) =>
      experiences.push((event as CustomEvent).detail.experience);
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);

    const cold = render(<Host snapshot={{ ...IDLE, loading: true }} />);
    act(() =>
      cold.rerender(
        <Host
          snapshot={{
            ...IDLE,
            allTerminal: true,
            researchStates: ["done"],
          }}
        />,
      ),
    );
    expect(experiences).toEqual([]);
    cold.unmount();

    notifyResearchStarted("session-local");
    const local = render(
      <Host
        snapshot={{
          ...IDLE,
          sessionId: "session-local",
          loading: true,
        }}
      />,
    );
    act(() =>
      local.rerender(
        <Host
          snapshot={{
            ...IDLE,
            sessionId: "session-local",
            allTerminal: true,
            researchStates: ["done"],
          }}
        />,
      ),
    );
    expect(experiences).toEqual([
      "deep_research_start",
      "deep_research_complete",
    ]);
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });
});
