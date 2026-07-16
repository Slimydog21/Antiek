import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BacktestView, type BacktestReport } from "./index";

const base: BacktestReport = {
  synthesis_id: "syn-1",
  synthesis_timestamp: "2026-01-01T00:00:00Z",
  target_question: "Will the decision survive new evidence?",
  status: "conditional",
  implicit_recommendation: null,
  substrate_manifest_counts: { chunks: 2 },
  added_edges_since: 200,
  superseded_edges_since: 40,
  cited_edges_now_superseded_count: 0,
  chunks_retired_downward_count: 0,
  outcomes_recorded: 0,
  cited_edges_now_superseded: [],
  chunks_retired_downward: [],
  outcomes: [],
};
const view = (
  report: BacktestReport | null = base,
  state: "ready" | "loading" | "not-found" | "error" = "ready",
  onRetry?: () => void,
) =>
  render(
    <MemoryRouter>
      <BacktestView
        synthesisId="syn-1"
        report={report}
        state={state}
        onRetry={onRetry}
      />
    </MemoryRouter>,
  );
afterEach(cleanup);

describe("BacktestView", () => {
  it("separates global graph churn from load-bearing evidence", () => {
    view();
    expect(
      screen.getByRole("heading", { name: "What changed around it" }),
    ).toBeTruthy();
    expect(screen.getByText(/not evidence for or against/i)).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "No cited-evidence drift found" }),
    ).toBeTruthy();
    expect(
      screen.getByText(/does not establish that the synthesis remains true/i),
    ).toBeTruthy();
  });
  it("renders cited edge and chunk semantics without raw JSON", () => {
    const report = {
      ...base,
      cited_edges_now_superseded_count: 1,
      chunks_retired_downward_count: 1,
      cited_edges_now_superseded: [
        {
          edge_id: "edge-1",
          source: "Claim A",
          relation: "depends on",
          target: "Claim B",
          valid_until: "2026-02-01T00:00:00Z",
          superseded_by: null,
        },
      ],
      chunks_retired_downward: [
        {
          chunk_id: "chunk-1",
          original_tier: 1,
          override_tier: 3,
          reason: "Failed replication",
          set_at: "2026-02-02T00:00:00Z",
        },
      ],
    };
    view(report);
    expect(
      screen.getByRole("heading", { name: "Cited evidence needs review" }),
    ).toBeTruthy();
    expect(screen.getByText("Claim A")).toBeTruthy();
    expect(screen.getByText("Tier 1 → Tier 3")).toBeTruthy();
    expect(document.body.textContent).not.toContain('{"edge_id"');
  });
  it("exposes summary/detail disagreement rather than smoothing it over", () => {
    view({ ...base, cited_edges_now_superseded_count: 3 });
    expect(screen.getByRole("status").textContent).toContain("summary says 3");
    expect(screen.getByRole("status").textContent).toContain("0 detail rows");
  });
  it("renders human observations as observations, never a confidence score", () => {
    view({
      ...base,
      outcomes_recorded: 1,
      outcomes: [
        {
          outcome_id: "o-1",
          observer: "Field council",
          observed_at: "2026-03-01T00:00:00Z",
          thesis_outcomes: [
            {
              thesis_claim: "Latency stays low",
              outcome: "partially_confirmed",
              evidence: "Mixed field result",
            },
          ],
          execution_risk_outcomes: [],
        },
      ],
    });
    const section = screen
      .getByRole("heading", { name: "Human-recorded outcomes" })
      .closest("section")!;
    expect(within(section).getByText("Field council")).toBeTruthy();
    expect(within(section).getByText("partially confirmed")).toBeTruthy();
    expect(screen.queryByText(/confidence score:|overall grade:/i)).toBeNull();
  });
  it("uses bounded fallbacks for malformed detail", () => {
    view({
      ...base,
      cited_edges_now_superseded_count: 1,
      cited_edges_now_superseded: [{ edge_id: "partial" }],
    });
    expect(screen.getByText("Detail unavailable in this report.")).toBeTruthy();
    expect(document.body.textContent).not.toContain("partial");
  });
  it("bounds malformed chunk and observer rows", () => {
    view({
      ...base,
      chunks_retired_downward_count: 1,
      outcomes_recorded: 1,
      chunks_retired_downward: [{ chunk_id: "partial-chunk" }],
      outcomes: [{ observer: "partial-observer" }],
    });
    expect(screen.getByText("Detail unavailable in this report.")).toBeTruthy();
    expect(
      screen.getByText("Observation detail unavailable in this report."),
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain("partial-chunk");
    expect(document.body.textContent).not.toContain("partial-observer");
  });
  it.each([
    ["loading", "Reading the instruments…"],
    ["not-found", "No archived synthesis found"],
    ["error", "The station could not load this report"],
  ] as const)("renders the %s state", (state, heading) => {
    view(null, state);
    expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
  });
  it("offers an explicit retry after safe failure", () => {
    const retry = vi.fn();
    view(null, "error", retry);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
