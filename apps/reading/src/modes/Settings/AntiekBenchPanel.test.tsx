import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import AntiekBenchPanel from "./AntiekBenchPanel";
import type { WeeklyBenchViewResponse } from "../../api/antiekBench";

afterEach(() => {
  cleanup();
});

function makeView(
  overrides: Partial<WeeklyBenchViewResponse> = {},
): WeeklyBenchViewResponse {
  return {
    week_id: "2026-W28",
    authority: "advisory",
    best_by_task: { deep_research: "thinker" },
    incomplete: false,
    notes: [],
    scores: [
      {
        task: "deep_research",
        model_id: "thinker",
        score: 0.9,
        n_runs: 2,
        notes: "",
      },
      {
        task: "deep_research",
        model_id: "flash",
        score: null,
        n_runs: 0,
        notes: "",
      },
    ],
    ...overrides,
  };
}

describe("AntiekBenchPanel", () => {
  it("shows advisory authority and NOT MEASURED for null scores", async () => {
    const fetchFn = vi.fn(async () => makeView());
    render(<AntiekBenchPanel fetchFn={fetchFn} />);
    fireEvent.click(screen.getByTestId("antiek-bench-load"));
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-result")).toBeTruthy();
    });
    expect(screen.getByTestId("antiek-bench-authority").textContent).toMatch(
      /advisory/i,
    );
    expect(
      screen.getByTestId("score-deep_research-flash").textContent,
    ).toMatch(/NOT MEASURED/);
    expect(
      screen.getByTestId("score-deep_research-thinker").textContent,
    ).toMatch(/0\.900/);
  });

  it("empty best_by_task shows none", async () => {
    const fetchFn = vi.fn(async () =>
      makeView({
        best_by_task: {},
        incomplete: true,
        scores: [],
      }),
    );
    render(<AntiekBenchPanel fetchFn={fetchFn} />);
    fireEvent.click(screen.getByTestId("antiek-bench-load"));
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-best").textContent).toMatch(
        /none/i,
      );
    });
  });

  it("shows error when fetch throws", async () => {
    const fetchFn = vi.fn(async () => {
      throw new Error("backend down");
    });
    render(<AntiekBenchPanel fetchFn={fetchFn} />);
    fireEvent.click(screen.getByTestId("antiek-bench-load"));
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-error").textContent).toMatch(
        /backend down/,
      );
    });
  });
});
