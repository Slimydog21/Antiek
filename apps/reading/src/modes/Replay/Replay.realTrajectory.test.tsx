import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import type { Event } from "../../generated/types";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", () => ({
  API_BASE: "",
  apiFetch: apiFetchMock,
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => (
    <div data-testid="panel-host">{children}</div>
  ),
}));

import Replay from ".";

class MockWebSocket {
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;

  constructor() {
    setTimeout(() => this.onopen?.(), 0);
  }

  close() {
    this.onclose?.();
  }
}

function event(
  eventId: string,
  emittedAt: string,
  actionType: Event["action_type"],
  role: string,
  payload: Record<string, unknown>,
  phase?: number,
): Event {
  return {
    event_id: eventId,
    investigation_id: "inv-real-multi-step",
    action_type: actionType,
    role,
    payload: {
      action_type: actionType,
      ...payload,
    } as never,
    phase,
    param_version: "0.1.0",
    schema_version: 33,
    emitted_at: emittedAt,
  };
}

const REALISTIC_MULTI_STEP_TRAJECTORY: Event[] = [
  event(
    "evt-006-complete",
    "2026-07-01T12:00:06Z",
    "investigation.completed",
    "orchestrator",
    { final_state: "sealed" },
    6,
  ),
  event(
    "evt-002-decompose",
    "2026-07-01T12:00:02Z",
    "decompose.delivered",
    "decomposer",
    { questions: ["What evidence constrains the claim?"] },
    2,
  ),
  event(
    "evt-004-evidence",
    "2026-07-01T12:00:04Z",
    "evidence.retrieve.delivered",
    "evidence_retriever",
    { citations: [{ title: "Mechanism note", source_tier: 2 }] },
    4,
  ),
  event(
    "evt-001-start",
    "2026-07-01T12:00:01Z",
    "investigation.start_requested",
    "operator",
    { question: "Can the trajectory replay prove a real multi-step run?" },
    1,
  ),
  event(
    "evt-005-synthesis",
    "2026-07-01T12:00:05Z",
    "synthesize.delivered",
    "synthesizer",
    { answer_document_id: "doc-answer-1" },
    5,
  ),
  event(
    "evt-003-dispatch",
    "2026-07-01T12:00:03Z",
    "dispatch.call",
    "router",
    { provider: "openai", model: "gpt-5.5", cost_usd: 0.018 },
    3,
  ),
];

function mountReplay() {
  return render(
    <MemoryRouter initialEntries={["/replay/inv-real-multi-step"]}>
      <Routes>
        <Route path="/replay/:investigationId" element={<Replay />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("Replay route with a realistic multi-step trajectory", () => {
  it("loads, sorts, renders, and scrubs a fetched investigation trajectory", async () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ events: REALISTIC_MULTI_STEP_TRAJECTORY }),
    });

    mountReplay();

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/trajectory/inv-real-multi-step",
      );
      expect(screen.getByText("· 6 events")).toBeTruthy();
    });

    expect(screen.getByText("1 / 6")).toBeTruthy();
    expect(screen.getByText(/event_id: evt-001-start/)).toBeTruthy();
    expect(
      screen.getAllByText(/investigation.start_requested/).length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText(/Can the trajectory replay prove a real multi-step run/),
    ).toBeTruthy();

    fireEvent.change(screen.getByRole("slider"), { target: { value: "5" } });

    expect(screen.getByText("6 / 6")).toBeTruthy();
    expect(screen.getByText(/event_id: evt-006-complete/)).toBeTruthy();
    expect(
      screen.getAllByText(/investigation.completed/).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/sealed/)).toBeTruthy();
  });
});
