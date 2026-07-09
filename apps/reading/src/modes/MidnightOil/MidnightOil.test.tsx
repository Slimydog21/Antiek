import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MidnightOil from "./index";

const createMidnightOilJob = vi.fn();
const approveMidnightOilCeiling = vi.fn();

vi.mock("../../api/midnightOil", () => ({
  createMidnightOilJob: (...args: unknown[]) => createMidnightOilJob(...args),
  approveMidnightOilCeiling: (...args: unknown[]) =>
    approveMidnightOilCeiling(...args),
  getMidnightOilJob: vi.fn(),
}));

describe("MidnightOil mode", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    createMidnightOilJob.mockReset();
    approveMidnightOilCeiling.mockReset();
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
});
