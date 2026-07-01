import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Event } from "../generated/types";
import type { InvestigationStatus } from "../lib/api";
import { getInvestigationStatus, getTrajectory } from "../lib/api";
import { useEventStream } from "./useEventStream";
import { useInvestigation } from "./useInvestigation";

vi.mock("../lib/api", () => ({
  getInvestigationStatus: vi.fn(),
  getTrajectory: vi.fn(),
}));

vi.mock("./useEventStream", () => ({
  useEventStream: vi.fn(),
}));

const getTrajectoryMock = vi.mocked(getTrajectory);
const getInvestigationStatusMock = vi.mocked(getInvestigationStatus);
const useEventStreamMock = vi.mocked(useEventStream);

afterEach(() => {
  vi.clearAllMocks();
});

const status = (over: Partial<InvestigationStatus> = {}): InvestigationStatus => ({
  investigation_id: "inv-1",
  status: "in_progress",
  current_phase: null,
  last_delivered_action_type: null,
  terminal_payload: null,
  rubric_score: null,
  ...over,
});

const event = (
  id: string,
  actionType: string,
  payload: Record<string, unknown> = {},
): Event =>
  ({
    event_id: id,
    investigation_id: "inv-1",
    action_type: actionType,
    payload: { action_type: actionType, ...payload },
    param_version: "v1",
    emitted_at: `2026-07-01T12:00:0${id.slice(-1)}Z`,
  }) as unknown as Event;

describe("useInvestigation", () => {
  it("ignores non-finite and negative dispatch costs", async () => {
    getTrajectoryMock.mockResolvedValue({
      investigation_id: "inv-1",
      count: 5,
      events: [
        event("e1", "investigation.start_requested", { question: "What changed?" }),
        event("e2", "dispatch.call", { cost_usd: 0.25 }),
        event("e3", "dispatch.call", { cost_usd: Number.NaN }),
        event("e4", "dispatch.call", { cost_usd: Number.POSITIVE_INFINITY }),
        event("e5", "dispatch.call", { cost_usd: -1 }),
      ],
    });
    getInvestigationStatusMock.mockResolvedValue(status());
    useEventStreamMock.mockReturnValue({
      events: [event("e6", "dispatch.call", { cost_usd: 0.125 })],
      status: "open",
      reconnects: 0,
    });

    const { result } = renderHook(() => useInvestigation("inv-1"));

    await waitFor(() => expect(result.current.status).toBe("in_progress"));
    expect(result.current.costTotal).toBe(0.375);
  });

  it("drops malformed seed trajectory rows before deriving investigation state", async () => {
    getTrajectoryMock.mockResolvedValue({
      investigation_id: "inv-1",
      count: 3,
      events: [
        event("e1", "investigation.start_requested", { question: "What changed?" }),
        {
          event_id: "e2",
          investigation_id: "inv-1",
          action_type: "not.a.real.action",
          payload: { action_type: "not.a.real.action" },
          param_version: "v1",
          emitted_at: "2026-07-01T12:00:02Z",
        } as unknown as Event,
        {
          ...event("e3", "dispatch.call", { cost_usd: 999 }),
          payload: { action_type: "phase.enter" },
        } as unknown as Event,
      ],
    });
    getInvestigationStatusMock.mockResolvedValue(status());
    useEventStreamMock.mockReturnValue({
      events: [event("e4", "dispatch.call", { cost_usd: 0.125 })],
      status: "open",
      reconnects: 0,
    });

    const { result } = renderHook(() => useInvestigation("inv-1"));

    await waitFor(() => expect(result.current.status).toBe("in_progress"));
    expect(result.current.question).toBe("What changed?");
    expect(result.current.events.map((e) => e.event_id)).toEqual(["e1", "e4"]);
    expect(result.current.costTotal).toBe(0.125);
  });
});
