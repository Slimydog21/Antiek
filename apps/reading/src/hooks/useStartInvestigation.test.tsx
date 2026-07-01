import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Event } from "../generated/types";
import { useEventStream } from "./useEventStream";
import { useStartInvestigation } from "./useStartInvestigation";

vi.mock("./useEventStream", () => ({
  useEventStream: vi.fn(),
}));

const useEventStreamMock = vi.mocked(useEventStream);

afterEach(() => {
  vi.clearAllMocks();
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
    payload,
    param_version: "v1",
    emitted_at: `2026-07-01T12:00:0${id.slice(-1)}Z`,
  }) as unknown as Event;

describe("useStartInvestigation", () => {
  it("ignores non-finite and negative live dispatch costs", () => {
    useEventStreamMock.mockReturnValue({
      events: [
        event("e1", "dispatch.call", { cost_usd: 0.25 }),
        event("e2", "dispatch.call", { cost_usd: Number.NaN }),
        event("e3", "dispatch.call", { cost_usd: Number.POSITIVE_INFINITY }),
        event("e4", "dispatch.call", { cost_usd: -1 }),
        event("e5", "dispatch.call", { cost_usd: 0.125 }),
      ],
      status: "open",
      reconnects: 0,
    });

    const { result } = renderHook(() => useStartInvestigation());

    expect(result.current.liveCost).toBe(0.375);
  });
});
