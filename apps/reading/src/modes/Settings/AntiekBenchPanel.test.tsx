import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AntiekBenchPanel from "./AntiekBenchPanel";

afterEach(cleanup);

describe("AntiekBenchPanel", () => {
  it("loads automatically and presents the best measured model per task", async () => {
    const fetchFn = vi.fn(async () => ({
      authority: "advisory" as const,
      status: "measured" as const,
      week_id: "2026-W28",
      generated_at: "2026-07-08T00:00:00+00:00",
      measurements: [
        {
          task: "reading" as const,
          tier: "pro",
          provider: "zai",
          model: "slow",
          score: 0.7,
          samples: 4,
        },
        {
          task: "reading" as const,
          tier: "flash",
          provider: "zai",
          model: "fast",
          score: 0.9,
          samples: 20,
        },
      ],
      notes: [],
    }));
    render(<AntiekBenchPanel fetchFn={fetchFn} />);
    expect(
      (await screen.findByTestId("antiek-bench-measured")).textContent,
    ).toMatch(/reading.*fast.*0\.900.*n=20/i);
    expect(fetchFn).toHaveBeenCalledWith();
    // Living-TV densify: session desk invent + Werner mark are UI-consumed.
    const desk = screen.getByTestId("antiek-bench-desk-art") as HTMLImageElement;
    expect(desk.getAttribute("src") ?? "").toMatch(
      /werner_antiek_bench_celebrate_session_v1/,
    );
    expect(screen.getByTestId("antiek-bench-werner")).toBeTruthy();
  });

  it("states unavailable evidence as not measured, never zero", async () => {
    render(
      <AntiekBenchPanel
        fetchFn={async () => ({
          authority: "advisory",
          status: "unavailable",
          week_id: null,
          generated_at: null,
          measurements: [],
          notes: ["report is not configured"],
        })}
      />,
    );
    const view = await screen.findByTestId("antiek-bench-unavailable");
    expect(view.textContent).toMatch(/not measured/i);
    expect(view.textContent).not.toContain("0.000");
  });

  it("surfaces errors and offers retry", async () => {
    render(
      <AntiekBenchPanel
        fetchFn={async () => {
          throw new Error("backend down");
        }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toMatch(/backend down/),
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });
});
