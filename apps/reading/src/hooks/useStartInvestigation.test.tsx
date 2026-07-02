import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Event } from "../generated/types";
import { useEventStream } from "./useEventStream";
import { useStartInvestigation } from "./useStartInvestigation";

const startInvestigationMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  startInvestigation: startInvestigationMock,
}));

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
  function closedStream() {
    useEventStreamMock.mockReturnValue({
      events: [],
      status: "closed",
      reconnects: 0,
    });
  }

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

  it("accepts numeric-string live dispatch costs", () => {
    useEventStreamMock.mockReturnValue({
      events: [
        event("e1", "dispatch.call", { cost_usd: "0.25" }),
        event("e2", "dispatch.call", { cost_usd: "0.125" }),
      ],
      status: "open",
      reconnects: 0,
    });

    const { result } = renderHook(() => useStartInvestigation());

    expect(result.current.liveCost).toBe(0.375);
  });

  it("sanitizes streamed failure reasons", () => {
    useEventStreamMock.mockReturnValue({
      events: [
        event("e1", "investigation.failed", { reason: ["not text"] }),
      ],
      status: "open",
      reconnects: 0,
    });

    const { result } = renderHook(() => useStartInvestigation());

    expect(result.current.failed).toBe(true);
    expect(result.current.failureReason).toBe("");
  });

  it("trims valid streamed failure reasons", () => {
    useEventStreamMock.mockReturnValue({
      events: [
        event("e1", "investigation.failed", { reason: " no provider " }),
      ],
      status: "open",
      reconnects: 0,
    });

    const { result } = renderHook(() => useStartInvestigation());

    expect(result.current.failed).toBe(true);
    expect(result.current.failureReason).toBe("no provider");
  });

  it("trims returned investigation ids before exposing started state", async () => {
    closedStream();
    startInvestigationMock.mockResolvedValue({
      investigation_id: " inv-started ",
      status: "in_progress",
      start_event_id: "e1",
    });
    const { result } = renderHook(() => useStartInvestigation());

    let started: string | null = null;
    await act(async () => {
      started = await result.current.submit({ question: "What changed?" });
    });

    expect(started).toBe("inv-started");
    expect(result.current.startedId).toBe("inv-started");
    expect(result.current.error).toBeNull();
  });

  it("surfaces malformed returned investigation ids as submit errors", async () => {
    closedStream();
    startInvestigationMock.mockResolvedValue({
      investigation_id: " ",
      status: "in_progress",
      start_event_id: "e1",
    });
    const { result } = renderHook(() => useStartInvestigation());

    let started: string | null = "not-null";
    await act(async () => {
      started = await result.current.submit({ question: "What changed?" });
    });

    expect(started).toBeNull();
    expect(result.current.startedId).toBeNull();
    expect(result.current.error).toMatch(/investigation_id must be a non-empty string/i);
  });
});
