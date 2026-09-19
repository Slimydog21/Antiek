import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, fireEvent } from "@testing-library/react";
import ComputeCapacityPanel from "./ComputeCapacityPanel";
import * as api from "../../api/settingsComputeCapacity";

vi.mock("../../api/settingsComputeCapacity", () => ({
  fetchComputeCapacity: vi.fn(),
  setComputeCapacity: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const sample = {
  owner_user_id: "owner-1",
  tier: "standard" as const,
  monthly_compute_units: 500,
  used_compute_units: null,
  used_status: "unmetered" as const,
  enforcement: "off" as const,
  updated_at: null,
  is_default: true,
  tier_presets: { starter: 100, standard: 500, power: 2000 },
  evaluation: {
    allowed: true,
    soft_over: false,
    would_hard_block: false,
    note: "used_unmetered_no_fake_billing",
  },
  note: "test",
};

describe("ComputeCapacityPanel", () => {
  it("loads and shows unmetered capacity", async () => {
    vi.mocked(api.fetchComputeCapacity).mockResolvedValue(sample);
    render(<ComputeCapacityPanel />);
    expect(await screen.findByTestId("compute-capacity-panel")).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText(/used=unmetered/)).toBeTruthy();
    });
    expect(screen.getByTestId("compute-capacity-slider")).toBeTruthy();
    expect(screen.getByTestId("compute-capacity-used-label").textContent).toMatch(
      /unmetered/,
    );
  });

  it("shows used ACU bar when meter is known", async () => {
    vi.mocked(api.fetchComputeCapacity).mockResolvedValue({
      ...sample,
      used_status: "known",
      used_compute_units: 420,
      enforcement: "soft",
      evaluation: {
        ...sample.evaluation,
        soft_over: true,
        note: "soft_over",
      },
    });
    render(<ComputeCapacityPanel />);
    expect(await screen.findByTestId("compute-capacity-used-bar")).toBeTruthy();
    expect(screen.getByTestId("compute-capacity-used-label").textContent).toContain(
      "420 / 500 ACU",
    );
    expect(screen.getByTestId("compute-capacity-soft-over")).toBeTruthy();
  });

  it("applies starter tier", async () => {
    vi.mocked(api.fetchComputeCapacity).mockResolvedValue(sample);
    vi.mocked(api.setComputeCapacity).mockResolvedValue({
      ...sample,
      tier: "starter",
      monthly_compute_units: 100,
      is_default: false,
    });
    render(<ComputeCapacityPanel />);
    await screen.findByTestId("compute-capacity-panel");
    fireEvent.click(screen.getByRole("button", { name: /Starter/ }));
    await waitFor(() => {
      expect(api.setComputeCapacity).toHaveBeenCalledWith({
        tier: "starter",
        monthly_compute_units: null,
      });
    });
  });
});
