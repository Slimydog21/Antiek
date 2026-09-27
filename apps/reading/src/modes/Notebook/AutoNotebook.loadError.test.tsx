/**
 * AutoNotebook.loadError.test.tsx — an outage is not "No research with id X"
 * (audit wave4 C15).
 *
 * Runs the REAL useInvestigation hook under AutoNotebook; only the api calls
 * and the live WS hook are stubbed. A trajectory fetch that fails (5xx or a
 * dropped connection) must render a retryable failure, and the retry must
 * recover. A 200 with zero events (how the backend answers an unknown id) is
 * the only path to the definite not-found sentence.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { getTrajectoryMock, getInvestigationStatusMock, getDistillationMock } = vi.hoisted(() => ({
  getTrajectoryMock: vi.fn(),
  getInvestigationStatusMock: vi.fn(),
  getDistillationMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    getTrajectory: getTrajectoryMock,
    getInvestigationStatus: getInvestigationStatusMock,
    getDistillation: getDistillationMock,
    getPromptTelemetry: vi.fn().mockRejectedValue(new Error("not under test")),
  };
});

vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: () => ({ events: [], status: "open", reconnects: 0 }),
}));

import { ApiError } from "../../lib/api";
import AutoNotebook from "./AutoNotebook";

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  (globalThis as unknown as { ResizeObserver: typeof FakeResizeObserver }).ResizeObserver =
    FakeResizeObserver;
  getInvestigationStatusMock.mockResolvedValue(null);
  getDistillationMock.mockResolvedValue({ investigation_id: "inv-123", insights: [], questions: [] });
});

afterEach(() => {
  cleanup();
  getTrajectoryMock.mockReset();
  getInvestigationStatusMock.mockReset();
  getDistillationMock.mockReset();
});

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/notebook/auto/${id}`]}>
      <Routes>
        <Route path="/notebook/auto/:investigationId" element={<AutoNotebook />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AutoNotebook — trajectory outage", () => {
  it.each([
    ["HTTP 503", () => new ApiError("GET /trajectory failed: HTTP 503", 503, "")],
    ["network", () => new TypeError("Failed to fetch")],
  ])("%s renders a retryable failure, not 'No research with id'", async (_l, make) => {
    getTrajectoryMock.mockRejectedValue(make());
    renderAt("inv-123");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn’t load this research");
    expect(screen.queryByText(/No research with id/)).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("retry re-fetches the trajectory and recovers", async () => {
    getTrajectoryMock.mockRejectedValueOnce(new ApiError("HTTP 503", 503, ""));
    getTrajectoryMock.mockResolvedValue({
      investigation_id: "inv-123",
      count: 1,
      events: [
        {
          event_id: "e1",
          action_type: "investigation.start_requested",
          emitted_at: "2026-09-01T00:00:00Z",
          payload: { question: "Real Q?" },
        },
      ],
    });
    renderAt("inv-123");

    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(getTrajectoryMock).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/No research with id/)).toBeNull();
  });

  it("CONTROL: a 200 with zero events still reads as not found", async () => {
    getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-123", count: 0, events: [] });
    renderAt("inv-123");
    expect(await screen.findByText(/No research with id/)).toBeTruthy();
  });
});
