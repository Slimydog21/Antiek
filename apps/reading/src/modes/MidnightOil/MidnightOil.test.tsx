import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MidnightOil from "./index";

const {
  createMidnightOilJob,
  approveMidnightOilCeiling,
  depositMidnightOilJob,
  getMidnightOilJob,
} = vi.hoisted(() => ({
  createMidnightOilJob: vi.fn(),
  approveMidnightOilCeiling: vi.fn(),
  depositMidnightOilJob: vi.fn(),
  getMidnightOilJob: vi.fn(),
}));

vi.mock("../../api/midnightOil", () => ({
  createMidnightOilJob,
  approveMidnightOilCeiling,
  depositMidnightOilJob,
  getMidnightOilJob,
}));

describe("MidnightOil mode", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    createMidnightOilJob.mockReset();
    approveMidnightOilCeiling.mockReset();
    depositMidnightOilJob.mockReset();
    getMidnightOilJob.mockReset();
  });

  it("creates job then approves at recommended ceiling", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_test",
      goals: ["Map residual risks"],
      duration_minutes: 60,
      status: "awaiting_approval",
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
      html: "<p>Midnight Oil job receipt</p>",
    });
    approveMidnightOilCeiling.mockResolvedValue({
      job_id: "moil_test",
      goals: ["Map residual risks"],
      duration_minutes: 60,
      status: "approved",
      recommended_price_ceiling_usd: 3.6,
      approved_ceiling_usd: 3.6,
      view_format: "html",
      runnable: true,
      html: "<p>Approved</p>",
    });

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/goals/i), {
      target: { value: "Map residual risks" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("recommended-ceiling").textContent).toContain(
        "3.60",
      );
    });

    fireEvent.click(
      screen.getByRole("button", { name: /approve at recommended/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("approved-ceiling").textContent).toContain(
        "3.60",
      );
    });
    expect(approveMidnightOilCeiling).toHaveBeenCalledWith({
      job_id: "moil_test",
      use_recommended: true,
    });
  });

  it("deposits results and shows progress after approve", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_dep",
      goals: ["Wrestle with twin notes"],
      duration_minutes: 30,
      status: "awaiting_approval",
      recommended_price_ceiling_usd: 2.0,
      view_format: "html",
      runnable: false,
      html: "<p>Receipt</p>",
    });
    approveMidnightOilCeiling.mockResolvedValue({
      job_id: "moil_dep",
      goals: ["Wrestle with twin notes"],
      duration_minutes: 30,
      status: "approved",
      recommended_price_ceiling_usd: 2.0,
      approved_ceiling_usd: 2.0,
      view_format: "html",
      runnable: true,
      html: "<p>Approved</p>",
    });
    depositMidnightOilJob.mockResolvedValue({
      job_id: "moil_dep",
      asset_id: "moil_asset_dep",
      document_id: "draft_moil_asset_dep_abc",
      twin_count: 2,
      spawn_ids: ["spn_1"],
      draft_combined: true,
      usage_recorded: true,
      progress_seeded: true,
      progress: {
        spawn_id: "spn_1",
        event_count: 5,
        latest_stage: "complete",
        is_terminal: true,
        view_format: "html",
        html: "<p>Deep research progress · complete</p>",
        events: [],
      },
      job_status: "complete",
      view_format: "html",
      html: "<p>Deposited HTML research asset</p>",
      notes: ["Deposit lands HTML research asset + twin notes."],
    });

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/goals/i), {
      target: { value: "Wrestle with twin notes" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => expect(screen.getByTestId("moil-job")).toBeTruthy());
    fireEvent.click(
      screen.getByRole("button", { name: /approve at recommended/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("moil-deposit")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("moil-deposit"));
    await waitFor(() => {
      expect(depositMidnightOilJob).toHaveBeenCalledWith({
        job_id: "moil_dep",
        draft_combined: true,
        record_progress: true,
        mark_complete: true,
        include_progress_html: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-deposit-result").textContent).toMatch(
        /twins=2/,
      );
    });
    expect(screen.getByTestId("moil-progress-summary").textContent).toMatch(
      /complete/,
    );
    expect(screen.getByTestId("deposit-html").innerHTML).toMatch(/Deposited HTML/);
    expect(
      screen.getByTestId("midnight-oil-mode").getAttribute("data-view-format"),
    ).toBe("html");
  });
});
