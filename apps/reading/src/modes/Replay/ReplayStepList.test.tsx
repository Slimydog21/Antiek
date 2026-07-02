import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";

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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

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

  it("accepts bare trajectory arrays while still dropping malformed rows", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => [
        event("valid-array", "investigation.completed", { phase: 8 }),
        {
          event_id: "bad-array-action",
          investigation_id: "inv-1",
          action_type: "not.a.real.action",
          payload: { action_type: "not.a.real.action" },
          param_version: "test",
          emitted_at: "2026-07-01T12:00:01Z",
        },
      ],
    });

    render(<ReplayStepList investigationId="inv-1" />);

    await waitFor(() => expect(screen.getByText("Steps · 1")).toBeTruthy());
    expect(screen.getByText("investigation · completed")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/bad-array/);
  });

  it("drops blank and duplicate event ids before creating replay step buttons", async () => {
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        events: [
          event(" replay-step ", "synthesize.delivered", {
            emitted_at: " 2026-07-01T12:00:00Z ",
          }),
          event("replay-step", "evidence.retrieve.delivered", {
            emitted_at: "2026-07-01T12:00:01Z",
          }),
          event(" ", "investigation.completed", {
            emitted_at: "2026-07-01T12:00:02Z",
          }),
        ],
      }),
    });

    render(<ReplayStepList investigationId="inv-1" />);

    await waitFor(() => expect(screen.getByText("Steps · 1")).toBeTruthy());
    expect(screen.getByText("synthesize ✓")).toBeTruthy();
    expect(screen.queryByText("evidence · retrieve ✓")).toBeNull();
    expect(screen.queryByText("investigation · completed")).toBeNull();

    screen.getByText("synthesize ✓").closest("button")?.click();
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        detail: { eventId: "replay-step" },
      }),
    );
    dispatchSpy.mockRestore();
  });

  it("keeps stale polled steps from overwriting the active investigation", async () => {
    const stale = deferred<{
      ok: true;
      json: () => Promise<{ events: Event[] }>;
    }>();
    const fresh = deferred<{
      ok: true;
      json: () => Promise<{ events: Event[] }>;
    }>();
    apiFetchMock.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);

    const rendered = render(<ReplayStepList investigationId="inv-stale" />);
    rendered.rerender(<ReplayStepList investigationId="inv-fresh" />);

    await act(async () => {
      fresh.resolve({
        ok: true,
        json: async () => ({
          events: [
            event("fresh-step", "synthesize.delivered", {
              investigation_id: "inv-fresh",
              emitted_at: "2026-07-01T12:00:10Z",
            }),
          ],
        }),
      });
    });

    expect(await screen.findByText("synthesize ✓")).toBeTruthy();
    expect(screen.getByText("2026-07-01T12:00:10Z")).toBeTruthy();

    await act(async () => {
      stale.resolve({
        ok: true,
        json: async () => ({
          events: [
            event("stale-step", "evidence.retrieve.delivered", {
              investigation_id: "inv-stale",
              emitted_at: "2026-07-01T12:00:00Z",
            }),
          ],
        }),
      });
    });

    expect(screen.getByText("synthesize ✓")).toBeTruthy();
    expect(screen.queryByText("evidence · retrieve ✓")).toBeNull();
    expect(screen.queryByText("2026-07-01T12:00:00Z")).toBeNull();
  });
});
