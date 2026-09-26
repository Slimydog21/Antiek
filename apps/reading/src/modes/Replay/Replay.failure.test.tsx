/**
 * FFX SPR-03 (F-07): /replay/:id rendered "GET /trajectory failed: HTTP n".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("../../components/TrajectoryReplay", () => ({
  default: ({ events }: { events: unknown[] }) => <p>{events.length} events replayed</p>,
}));

import Replay from "./index";

class FakeWebSocket {
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  close() {}
}

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("WebSocket", FakeWebSocket);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The `what` passed to describeFailure is plain words, so the title is
 *  "Couldn't <what>." and not the "That didn't work." fallback (#3538). */
function expectPlainTitle(text: string) {
  expect(text).toMatch(/^Couldn't [a-z][a-z ']*\./i);
}

function expectHonest(text: string) {
  expect(text).not.toMatch(/\b[45]\d\d\b/);
  expect(text).not.toMatch(/\/[a-z-]+/);
  expect(text).not.toContain("Failed to fetch");
  expect(text).not.toContain("HTTP");
}

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/replay/${id}`]}>
      <Routes>
        <Route path="/replay/:investigationId" element={<Replay />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Replay — honest failure", () => {
  it("a 503 shows plain copy and Try again re-reads the trajectory", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "x" }), { status: 503 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ events: [{ event_id: "e1" }] }), { status: 200 }),
      );
    renderAt("inv-1");
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't load this replay.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("1 events replayed")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(String(fetchMock.mock.calls[1][0])).toBe(String(fetchMock.mock.calls[0][0]));
  });

  it("a network TypeError never shows 'Failed to fetch'", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderAt("inv-1");
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
  });
});
