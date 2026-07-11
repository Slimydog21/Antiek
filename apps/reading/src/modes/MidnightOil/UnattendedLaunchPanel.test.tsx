import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import UnattendedLaunchPanel from "./UnattendedLaunchPanel";
import type { UnattendedBriefResult } from "../../api/unattendedLaunch";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: UnattendedBriefResult = {
  duration_minutes: 90,
  goals: ["deep research"],
  approved_ceiling_cents: 250,
  recommended_ceiling_cents: 200,
  notes: ["live_execution_authorized=false"],
  live_execution_authorized: false,
  authority: "operator_brief_only",
};

describe("UnattendedLaunchPanel", () => {
  it("validates brief via injectable briefFn", async () => {
    const briefFn = vi.fn(async () => sample);
    render(
      <UnattendedLaunchPanel
        briefFn={briefFn}
        initialDurationMinutes={90}
        initialGoals={"deep research\n"}
        initialApprovedCeilingCents={250}
        initialRecommendedCeilingCents={200}
      />,
    );
    fireEvent.click(screen.getByTestId("unattended-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("unattended-summary").textContent).toMatch(
        /90 min/,
      );
    });
    expect(screen.getByTestId("unattended-live").textContent).toMatch(
      /false/,
    );
    expect(briefFn).toHaveBeenCalledWith({
      duration_minutes: 90,
      goals: ["deep research"],
      approved_ceiling_cents: 250,
      recommended_ceiling_cents: 200,
    });
  });

  it("surfaces errors without success result", async () => {
    const briefFn = vi.fn(async () => {
      throw new Error("goals must contain at least one goal");
    });
    render(<UnattendedLaunchPanel briefFn={briefFn} />);
    fireEvent.click(screen.getByTestId("unattended-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("unattended-error").textContent).toMatch(
        /goals/,
      );
    });
    expect(screen.queryByTestId("unattended-result")).toBeNull();
  });

  it("rejects injectable live_execution_authorized true", async () => {
    const briefFn = vi.fn(async () => ({
      ...sample,
      live_execution_authorized: true,
    }));
    render(
      <UnattendedLaunchPanel
        briefFn={briefFn}
        initialGoals="x"
        initialDurationMinutes={30}
        initialApprovedCeilingCents={1}
      />,
    );
    fireEvent.click(screen.getByTestId("unattended-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("unattended-error").textContent).toMatch(
        /live_execution_authorized/,
      );
    });
    expect(screen.queryByTestId("unattended-result")).toBeNull();
  });
});
