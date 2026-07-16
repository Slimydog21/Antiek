import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Event } from "../../generated/types";
import { apiFetch } from "../../lib/api";
import TrajectoryReplay from "../../components/TrajectoryReplay";
import Replay from "./index";
import ReplayStepList from "./ReplayStepList";
import { ReplayProvider, useReplay } from "./ReplayContext";

vi.mock("../../lib/api", () => ({ API_BASE: "", apiFetch: vi.fn() }));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const event = (id: string, action = "decompose.delivered", time = "2026-01-01T00:00:00Z") => ({
  event_id: id,
  investigation_id: "inv-one",
  action_type: action,
  emitted_at: time,
  phase: 1,
  role: "researcher",
  payload: { summary: id },
}) as Event;

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  close = vi.fn();
  constructor(public url: string) { FakeSocket.instances.push(this); }
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Investigation replay observatory", () => {
  it("hard-locks deterministic fixtures without HTTP or socket execution", () => {
    render(<MemoryRouter><Replay investigationId="inv-one" executionEnabled={false} initialEvents={[event("a")]} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Return to the trail of thought." })).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("owns one exact history request and live socket, dropping ping, malformed, and duplicate frames", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ok: true, json: async () => ({ events: [event("a")] }) } as Response);
    const view = render(<ReplayProvider investigationId="inv / one"><ReplayProbe /></ReplayProvider>);
    await waitFor(() => expect(screen.getByText("a")).toBeTruthy());
    expect(apiFetch).toHaveBeenCalledWith("/trajectory/inv%20%2F%20one");
    expect(FakeSocket.instances[0]?.url).toContain("/ws/events?investigation_id=inv%20%2F%20one");
    const socket = FakeSocket.instances[0];
    socket.onmessage?.({ data: JSON.stringify({ type: "ping" }) } as MessageEvent);
    socket.onmessage?.({ data: JSON.stringify({ action_type: "missing-id" }) } as MessageEvent);
    socket.onmessage?.({ data: "not-json" } as MessageEvent);
    socket.onmessage?.({ data: JSON.stringify(event("a")) } as MessageEvent);
    socket.onmessage?.({ data: JSON.stringify(event("b")) } as MessageEvent);
    expect(await screen.findByText("a,b")).toBeTruthy();
    view.unmount();
    expect(socket.close).toHaveBeenCalledOnce();
  });

  it("closes the old live tail and opens exact new authorities when the route changes", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ events: [event("old")] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ events: [event("new")] }) } as Response);
    const view = render(<ReplayProvider investigationId="inv-one"><ReplayProbe /></ReplayProvider>);
    expect(await screen.findByText("old")).toBeTruthy();
    const firstSocket = FakeSocket.instances[0];
    view.rerender(<ReplayProvider investigationId="inv-two"><ReplayProbe /></ReplayProvider>);
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(2));
    expect(await screen.findByText("new")).toBeTruthy();
    expect(screen.queryByText("old")).toBeNull();
    expect(firstSocket.close).toHaveBeenCalledOnce();
    expect(apiFetch).toHaveBeenNthCalledWith(1, "/trajectory/inv-one");
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/trajectory/inv-two");
    expect(FakeSocket.instances[1]?.url).toContain("investigation_id=inv-two");
  });

  it("merges an early live event with later history without loss or duplication", async () => {
    let resolveHistory!: (response: Response) => void;
    vi.mocked(apiFetch).mockReturnValue(new Promise((resolve) => { resolveHistory = resolve; }));
    render(<ReplayProvider investigationId="inv-one"><ReplayProbe /></ReplayProvider>);
    const socket = FakeSocket.instances[0];
    socket.onmessage?.({ data: JSON.stringify(event("live")) } as MessageEvent);
    expect(await screen.findByText("live")).toBeTruthy();
    resolveHistory({
      ok: true,
      json: async () => ({ events: [event("history"), event("live")] }),
    } as Response);
    expect(await screen.findByText("history,live")).toBeTruthy();
  });

  it("keeps the dock list network-free and preserves the goto event", () => {
    const listener = vi.fn();
    window.addEventListener("antiek:replay:goto", listener);
    render(<ReplayProvider executionEnabled={false} initialEvents={[event("step-a")]}><ReplayStepList investigationId="inv-one" /></ReplayProvider>);
    fireEvent.click(screen.getByRole("button", { name: /decompose/i }));
    expect(listener).toHaveBeenCalledOnce();
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual({ eventId: "step-a" });
    expect(apiFetch).not.toHaveBeenCalled();
    window.removeEventListener("antiek:replay:goto", listener);
  });

  it("keeps the selected event stable when a late earlier event changes sorting", () => {
    const { rerender } = render(<TrajectoryReplay events={[event("b", "connector.delivered", "2026-01-02T00:00:00Z"), event("c", "synthesize.delivered", "2026-01-03T00:00:00Z")]} />);
    fireEvent.change(screen.getByLabelText("Replay event position"), { target: { value: "1" } });
    expect(screen.getByText("event_id: c")).toBeTruthy();
    rerender(<TrajectoryReplay events={[event("a", "decompose.delivered", "2026-01-01T00:00:00Z"), event("b", "connector.delivered", "2026-01-02T00:00:00Z"), event("c", "synthesize.delivered", "2026-01-03T00:00:00Z")]} />);
    expect(screen.getByText("event_id: c")).toBeTruthy();
    expect((screen.getByLabelText("Replay event position") as HTMLInputElement).value).toBe("2");
  });

  it("exposes accessible playback state, range meaning, and a non-grading boundary", () => {
    render(<MemoryRouter><Replay investigationId="inv-one" executionEnabled={false} initialEvents={[event("a")]} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Play" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByLabelText("Replay event position").getAttribute("aria-valuetext")).toBe("Event 1 of 1");
    expect(screen.getByText(/does not grade, rank, or rewrite/)).toBeTruthy();
  });
});

function ReplayProbe() {
  const { events } = useReplay();
  return <span>{events.map((item) => item.event_id).join(",")}</span>;
}
