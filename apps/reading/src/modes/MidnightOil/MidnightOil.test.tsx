import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MidnightOil from "./index";
import { preflightMidnightOil } from "../../api/midnightOil";

vi.mock("../../api/midnightOil", () => ({
  preflightMidnightOil: vi.fn(async () => ({
    accepted: true,
    denial_reason: null,
    run_id: "midnight-oil-test",
    goal: "Explain widebody engine bottlenecks.",
    work_minutes: 90,
    price_ceiling_usd: 12,
    route_mode: "auto_cost",
    source_policy: ["arxiv", "substack", "operator_corpus"],
    deliverable: "html_research_asset",
    planned_budget_usd: 7.2,
    unallocated_budget_usd: 4.8,
    role_plans: [
      {
        role: "planner",
        budget_usd: 1.8,
        max_minutes: 13,
        route_mode: "auto_cost",
        route_receipt_required: true,
        source_receipts_required: true,
        planned_route_receipt_id: "midnight-oil-test-planner-route-receipt",
      },
      {
        role: "gatherer",
        budget_usd: 5.4,
        max_minutes: 45,
        route_mode: "auto_cost",
        route_receipt_required: true,
        source_receipts_required: true,
        planned_route_receipt_id: "midnight-oil-test-gatherer-route-receipt",
      },
    ],
    artifact_contract: {
      final_format: "html",
      pdf_allowed: false,
      antiek_information_asset: true,
      twin_note_document_required: true,
      route_receipt_links_required: true,
      source_receipt_links_required: true,
    },
    launch_packet: {
      packet_id: "midnight-oil-test-launch-packet",
      run_id: "midnight-oil-test",
      goal: "Explain widebody engine bottlenecks.",
      work_minutes: 90,
      price_ceiling_usd: 12,
      planned_budget_usd: 7.2,
      unallocated_budget_usd: 4.8,
      route_mode: "auto_cost",
      source_policy: ["arxiv", "substack", "operator_corpus"],
      deliverable: "html_research_asset",
      artifact_contract: {
        final_format: "html",
        pdf_allowed: false,
        antiek_information_asset: true,
        twin_note_document_required: true,
        route_receipt_links_required: true,
        source_receipt_links_required: true,
      },
      role_count: 2,
      role_route_receipt_ids: [
        "midnight-oil-test-planner-route-receipt",
        "midnight-oil-test-gatherer-route-receipt",
      ],
      source_receipts_required: true,
      route_receipts_required: true,
      dispatch_allowed: false,
      budget_reserved: false,
      provider_calls_made: false,
      launch_notes: ["launch packet only: no agents dispatched"],
    },
    approval_receipt: {
      receipt_id: "midnight-oil-test-approval-receipt",
      launch_packet_id: "midnight-oil-test-launch-packet",
      run_id: "midnight-oil-test",
      operator_acknowledged_spend: true,
      approved_price_ceiling_usd: 12,
      approved_work_minutes: 90,
      approved_route_mode: "auto_cost",
      approved_source_policy: ["arxiv", "substack", "operator_corpus"],
      approved_deliverable: "html_research_asset",
      planned_budget_usd: 7.2,
      unallocated_budget_usd: 4.8,
      approval_scope: "preflight_launch_packet_only",
      runner_apply_required: true,
      dispatch_allowed: false,
      budget_reserved: false,
      provider_calls_made: false,
      receipt_notes: ["operator approved the ceiling for this launch packet only"],
    },
    notes: ["preflight only: no agents launched, no budget reserved, no retrieval performed"],
  })),
}));

describe("MidnightOil", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => cleanup());

  it("submits a no-launch autonomous research preflight and renders the contract", async () => {
    const user = userEvent.setup();
    render(<MidnightOil />);

    await user.type(
      screen.getByRole("textbox", { name: /goal/i }),
      "Explain widebody engine bottlenecks.",
    );
    fireEvent.change(screen.getByLabelText(/work minutes/i), { target: { value: "90" } });
    fireEvent.change(screen.getByLabelText(/price ceiling usd/i), { target: { value: "12" } });
    await user.selectOptions(screen.getByLabelText(/route mode/i), "auto_cost");
    await user.click(screen.getByRole("checkbox", { name: "Web" }));
    await user.click(screen.getByLabelText(/I approve this ceiling/i));
    await user.click(screen.getByRole("button", { name: "Preflight" }));

    await waitFor(() => expect(preflightMidnightOil).toHaveBeenCalled());
    expect(preflightMidnightOil).toHaveBeenCalledWith({
      goal: "Explain widebody engine bottlenecks.",
      work_minutes: 90,
      price_ceiling_usd: 12,
      route_mode: "auto_cost",
      source_policy: ["arxiv", "substack", "operator_corpus", "web"],
      deliverable: "html_research_asset",
      operator_acknowledged_spend: true,
    });

    expect(screen.getByText("midnight-oil-test")).toBeTruthy();
    expect(screen.getByText("$7.20")).toBeTruthy();
    expect(screen.getByText("$4.80")).toBeTruthy();
    expect(screen.getByText("Unallocated")).toBeTruthy();
    expect(screen.getByText("html")).toBeTruthy();
    expect(screen.getByText("Twin notes")).toBeTruthy();
    expect(screen.getByText("Launch packet")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-launch-packet")).toBeTruthy();
    expect(screen.getByText("Dispatch")).toBeTruthy();
    expect(screen.getByText("disabled")).toBeTruthy();
    expect(screen.getByText("Approval receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-approval-receipt")).toBeTruthy();
    expect(screen.getByText("Runner apply")).toBeTruthy();
    expect(screen.getAllByText("required").length).toBeGreaterThan(0);
    expect(screen.getByText(/no agents launched/i)).toBeTruthy();
  });
});
