import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import UnattendedLaunchGatePanel from "./UnattendedLaunchGatePanel";
import type { LaunchGateDecision } from "../../api/unattendedLaunchGate";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: LaunchGateDecision = {
  dispatch_ready: true,
  live_execution_authorized: false,
  zero_ceiling_dry_run: false,
  operator_approved: true,
  consent_receipt_id: "rcpt-1",
  brief: {
    duration_minutes: 90,
    goals: ["map X"],
    approved_ceiling_cents: 200,
    live_execution_authorized: false,
    authority: "operator_brief_only",
  },
  reasons: [],
  notes: [],
  authority: "launch_gate_advisory",
};

describe("UnattendedLaunchGatePanel", () => {
  it("evaluates via injectable gateFn", async () => {
    const gateFn = vi.fn(async () => sample);
    render(
      <UnattendedLaunchGatePanel
        gateFn={gateFn}
        initialDurationMinutes={90}
        initialGoals={"map X\n"}
        initialApprovedCeilingCents={200}
        initialConsentReceiptId="rcpt-1"
        initialOperatorApproved={true}
      />,
    );
    fireEvent.click(screen.getByTestId("ulg-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("ulg-dispatch").textContent).toMatch(
        /true/,
      );
    });
    expect(screen.getByTestId("ulg-live").textContent).toMatch(/false/);
    expect(gateFn).toHaveBeenCalledWith({
      operator_approved: true,
      consent_receipt_id: "rcpt-1",
      duration_minutes: 90,
      goals: ["map X"],
      approved_ceiling_cents: 200,
    });
  });

  it("surfaces errors", async () => {
    const gateFn = vi.fn(async () => {
      throw new Error("consent_receipt_id required");
    });
    render(
      <UnattendedLaunchGatePanel
        gateFn={gateFn}
        initialGoals="x"
        initialOperatorApproved={true}
        initialApprovedCeilingCents={100}
      />,
    );
    fireEvent.click(screen.getByTestId("ulg-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("ulg-error").textContent).toMatch(
        /consent_receipt_id/,
      );
    });
  });

  it("rejects live invent", async () => {
    const gateFn = vi.fn(async () => ({
      ...sample,
      live_execution_authorized: true,
    }));
    render(
      <UnattendedLaunchGatePanel
        gateFn={gateFn}
        initialGoals="x"
        initialOperatorApproved={true}
        initialApprovedCeilingCents={0}
      />,
    );
    fireEvent.click(screen.getByTestId("ulg-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("ulg-error").textContent).toMatch(
        /live_execution_authorized/,
      );
    });
  });
});
