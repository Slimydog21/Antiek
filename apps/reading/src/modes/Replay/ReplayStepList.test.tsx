import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import type { Event } from "../../generated/types";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

import ReplayStepList from "./ReplayStepList";

function event(
  id: string,
  actionType: Event["action_type"],
  over: Partial<Event> = {},
): Event {
  return {
    event_id: id,
    investigation_id: "inv-1",
    action_type: actionType,
    payload: { action_type: actionType } as Event["payload"],
    param_version: "test",
    emitted_at: "2026-07-01T12:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  apiFetchMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("ReplayStepList", () => {
  it("drops malformed trajectory rows before creating clickable replay steps", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        events: [
          event("valid", "synthesize.delivered", { phase: 3 }),
          {
            event_id: "bad-action",
            investigation_id: "inv-1",
            action_type: "not.a.real.action",
            payload: { action_type: "not.a.real.action" },
            param_version: "test",
            emitted_at: "2026-07-01T12:00:01Z",
          },
          {
            ...event("bad-mismatch", "investigation.completed"),
            payload: { action_type: "phase.enter" },
          },
          event("nan-phase", "evidence.retrieve.delivered", {
            phase: Number.NaN,
            emitted_at: "2026-07-01T12:00:02Z",
          }),
          event("insignificant", "dispatch.call", {
            emitted_at: "2026-07-01T12:00:03Z",
          }),
        ],
      }),
    });

    render(<ReplayStepList investigationId="inv-1" />);

    await waitFor(() => expect(screen.getByText("Steps · 2")).toBeTruthy());
    expect(screen.getByText("synthesize ✓")).toBeTruthy();
    expect(screen.getByText("evidence · retrieve ✓")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/bad-|dispatch|NaN|ph NaN/);
  });
});
