import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Loop3 from "./index";

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
      criteria: {
        " trajectory_volume ": true,
        sft_readiness: "yes",
        " ": true,
      },
      notes: {
        " trajectory_volume ": " enough trajectories ",
        " ": "Skipped note",
      },
      all_criteria_met: "yes",
      env_unlocked: "yes",
      fully_unlocked: "yes",
      evidence: {
        criteria: {
          " trajectory_volume ": true,
          sft_readiness: "yes",
        },
        statuses: {
          " trajectory_volume ": {
            criterion: " trajectory_volume ",
            status: " pass ",
            passed: true,
            summary: " trajectory evidence passed ",
          },
          sft_readiness: {
            criterion: " sft_readiness ",
            status: " pass ",
            passed: "yes",
            summary: " should not pass ",
          },
          " ": {
            criterion: "Skipped criterion",
            summary: "Skipped summary",
          },
        },
        all_evidence_passed: "yes",
        events_dir: " /tmp/events ",
        open_weight_policy_file: " /tmp/policy.md ",
      },
    }),
  });
});

afterEach(() => cleanup());

describe("Loop3", () => {
  it("sanitizes unlock status before rendering checklist state", async () => {
    render(<Loop3 />);

    expect(await screen.findByText("trajectory evidence passed")).toBeTruthy();
    expect(screen.getByDisplayValue("enough trajectories")).toBeTruthy();
    expect(screen.getAllByText("NO")).toHaveLength(3);
    expect(screen.getByText("FAIL")).toBeTruthy();
    expect(screen.getByText("should not pass")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Skipped|YES/);
  });
});
