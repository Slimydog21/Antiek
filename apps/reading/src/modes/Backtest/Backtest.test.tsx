import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Backtest from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      synthesis_id: " syn dirty ",
      synthesis_timestamp: " 2026-06-02T10:00:00Z ",
      target_question: " What changed? ",
      status: " current ",
      implicit_recommendation: " revisit ",
      substrate_manifest_counts: {
        nodes: "4.9",
        edges: Number.POSITIVE_INFINITY,
        " ": 100,
      },
      added_edges_since: "3.8",
      superseded_edges_since: -2,
      cited_edges_now_superseded_count: Number.POSITIVE_INFINITY,
      chunks_retired_downward_count: "2.2",
      outcomes_recorded: "NaN",
      cited_edges_now_superseded: [
        { edge_id: "edge-1" },
        "Skipped edge",
      ],
      chunks_retired_downward: [
        { chunk_id: "chunk-1" },
        null,
      ],
      outcomes: [
        { outcome_id: "outcome-1" },
        "Skipped outcome",
      ],
    }),
  });
});

afterEach(() => cleanup());

function renderBacktest() {
  return render(
    <MemoryRouter initialEntries={["/backtest/syn-route"]}>
      <Routes>
        <Route path="/backtest/:synthesisId" element={<Backtest />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Backtest", () => {
  it("sanitizes backtest reports before rendering metrics and detail rows", async () => {
    renderBacktest();

    expect(await screen.findByText("What changed?")).toBeTruthy();
    expect(
      screen.getByText(/2026-06-02T10:00:00Z · status=current · revisit/),
    ).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByText(JSON.stringify({ edge_id: "edge-1" }))).toBeTruthy();
    expect(
      screen.getByText(JSON.stringify({ chunk_id: "chunk-1" })),
    ).toBeTruthy();
    expect(
      screen.getByText(JSON.stringify({ outcome_id: "outcome-1" })),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /NaN|Infinity|-2|Skipped edge|Skipped outcome/,
    );
    expect(
      screen
        .getByRole("link", { name: /Open outcomes grading view/i })
        .getAttribute("href"),
    ).toBe("/outcomes/syn%20dirty");
  });
});
