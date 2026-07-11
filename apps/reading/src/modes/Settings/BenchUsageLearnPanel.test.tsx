import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import BenchUsageLearnPanel from "./BenchUsageLearnPanel";
import type { UsageLearnProposal } from "../../api/benchUsageLearn";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: UsageLearnProposal = {
  week_id: "2026-W28",
  authority: "advisory",
  incomplete: false,
  notes: ["authority=advisory — proposal only"],
  suggested_new_tasks: [],
  task_weights: [
    {
      task: "deep_research",
      weight: 0.66,
      prior_weight: null,
      n_success: 1,
      n_failure: 1,
      rationale: "balanced",
    },
  ],
};

describe("BenchUsageLearnPanel", () => {
  it("proposes via injectable proposeFn and shows advisory weights", async () => {
    const proposeFn = vi.fn(async () => sample);
    render(
      <BenchUsageLearnPanel
        proposeFn={proposeFn}
        initialWeekId="2026-W28"
        initialEventsJson='[{"task":"deep_research","success":false}]'
      />,
    );
    fireEvent.click(screen.getByTestId("bench-usage-learn-propose"));
    await waitFor(() => {
      expect(screen.getByTestId("bench-usage-learn-result")).toBeTruthy();
    });
    expect(proposeFn).toHaveBeenCalled();
    expect(screen.getByTestId("bench-usage-learn-authority").textContent).toMatch(
      /advisory/i,
    );
    expect(
      screen.getByTestId("bench-usage-learn-weight-deep_research").textContent,
    ).toMatch(/0\.6600/);
  });

  it("rejects injectable non-advisory authority without rendering result", async () => {
    const proposeFn = vi.fn(async () => ({
      ...sample,
      authority: "production",
    }));
    render(<BenchUsageLearnPanel proposeFn={proposeFn} />);
    fireEvent.click(screen.getByTestId("bench-usage-learn-propose"));
    await waitFor(() => {
      expect(screen.getByTestId("bench-usage-learn-error").textContent).toMatch(
        /advisory/,
      );
    });
    expect(screen.queryByTestId("bench-usage-learn-result")).toBeNull();
  });

  it("surfaces JSON parse errors", async () => {
    render(
      <BenchUsageLearnPanel
        proposeFn={vi.fn(async () => sample)}
        initialEventsJson="not-json"
      />,
    );
    fireEvent.click(screen.getByTestId("bench-usage-learn-propose"));
    await waitFor(() => {
      expect(screen.getByTestId("bench-usage-learn-error")).toBeTruthy();
    });
    expect(screen.queryByTestId("bench-usage-learn-result")).toBeNull();
  });
});
