/**
 * FFX SPR-03 (A-15, F-07): /backtest/does-not-exist rendered the whole
 * backtest surface around the 404, and other failures rendered
 * "GET /backtest: HTTP n".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Backtest from "./index";

const REPORT = {
  synthesis_id: "syn-1",
  synthesis_timestamp: "2026-09-27",
  target_question: "Does X cause Y?",
  status: "complete",
  implicit_recommendation: null,
  substrate_manifest_counts: { a: 1 },
  added_edges_since: 1,
  superseded_edges_since: 1,
  cited_edges_now_superseded_count: 0,
  chunks_retired_downward_count: 0,
  outcomes_recorded: 0,
  cited_edges_now_superseded: [],
  chunks_retired_downward: [],
  outcomes: [],
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
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
    <MemoryRouter initialEntries={[`/backtest/${id}`]}>
      <Routes>
        <Route path="/backtest/:synthesisId" element={<Backtest />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Backtest — nonexistent ids and honest failures", () => {
  it("a 404 renders 'That backtest isn't available.' with a way to outcomes, not the report surface", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "not_archived" }), { status: 404 }));
    renderAt("does-not-exist");
    expect(await screen.findByText("That backtest isn't available.")).toBeTruthy();
    const link = screen.getByRole("link", { name: /outcomes/i });
    expect(link.getAttribute("href")).toBe("/outcomes");
    expect(screen.queryByText(/How has the substrate changed/)).toBeNull();
    expect(screen.queryByText(/synthesis_id/)).toBeNull();
    expectHonest(document.body.textContent ?? "");
  });

  it("a 503 shows plain copy and Try again reloads the report", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "x" }), { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(REPORT), { status: 200 }));
    renderAt("syn-1");
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't load this backtest.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Does X cause Y?")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("a network TypeError never shows 'Failed to fetch'", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderAt("syn-1");
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
  });
});
