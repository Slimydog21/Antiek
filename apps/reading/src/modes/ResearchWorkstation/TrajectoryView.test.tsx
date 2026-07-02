import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";
import TrajectoryView from "./TrajectoryView";

afterEach(() => cleanup());

function ev(
  actionType: string,
  payload: Record<string, unknown> = {},
  extra: Partial<Event> = {},
): Event {
  return {
    event_id: "event-1",
    investigation_id: "inv-test",
    action_type: actionType as Event["action_type"],
    payload: payload as unknown as Event["payload"],
    param_version: "v1",
    emitted_at: "2026-07-01T12:00:00Z",
    ...extra,
  } as Event;
}

function state(overrides: Partial<InvestigationState>): InvestigationState {
  return {
    id: "inv-test",
    status: "in_progress",
    question: "Q",
    events: [],
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    ...overrides,
  };
}

describe("TrajectoryView", () => {
  it("treats malformed event collections as empty", () => {
    render(
      <TrajectoryView
        investigation={state({
          events: "not-an-array" as unknown as Event[],
          costTotal: Number.NaN,
        })}
      />,
    );

    expect(screen.getByText("$0.0000")).toBeTruthy();
    expect(screen.getByText("0 events")).toBeTruthy();
    expect(screen.getByText("Waiting for first phase to begin…")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });

  it("accepts numeric-string costs and phase tags in the raw timeline", () => {
    render(
      <TrajectoryView
        investigation={state({
          costTotal: "0.0731" as unknown as number,
          events: [
            ev(
              "decompose.delivered",
              {
                decomposition: [{ sub_question: "One angle" }],
              },
              { phase: "1" as unknown as number },
            ),
          ],
        })}
      />,
    );

    expect(screen.getByText("$0.0731")).toBeTruthy();
    expect(screen.getByText("1 events")).toBeTruthy();
    expect(screen.getByText("Phase 1 · Orientation + decomposition")).toBeTruthy();
    expect(screen.getByText("One angle")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });

  it("buckets malformed phase tags into phase 0", () => {
    render(
      <TrajectoryView
        investigation={state({
          events: [
            ev(
              "decompose.delivered",
              {
                decomposition: [{ sub_question: "Unphased angle" }],
              },
              { phase: Number.POSITIVE_INFINITY },
            ),
          ],
        })}
      />,
    );

    expect(screen.getByText("Phase 0")).toBeTruthy();
    expect(screen.getByText("Unphased angle")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });
});
