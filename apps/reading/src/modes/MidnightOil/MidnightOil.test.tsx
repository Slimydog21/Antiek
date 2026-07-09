import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MidnightOil from "./index";
import {
  activationChecklistMidnightOil,
  budgetReservationMidnightOil,
  dispatchMidnightOil,
  dryRunMidnightOil,
  preflightMidnightOil,
  providerRouteMidnightOil,
  retrievalMidnightOil,
} from "../../api/midnightOil";

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
    runner_handoff: {
      handoff_id: "midnight-oil-test-runner-handoff",
      approval_receipt_id: "midnight-oil-test-approval-receipt",
      launch_packet_id: "midnight-oil-test-launch-packet",
      run_id: "midnight-oil-test",
      status: "ready_for_runner_apply",
      approved_price_ceiling_usd: 12,
      planned_budget_usd: 7.2,
      unallocated_budget_usd: 4.8,
      role_route_receipt_ids: [
        "midnight-oil-test-planner-route-receipt",
        "midnight-oil-test-gatherer-route-receipt",
      ],
      prerequisite_receipt_ids: [
        "midnight-oil-test-launch-packet",
        "midnight-oil-test-approval-receipt",
      ],
      dispatch_ready: true,
      dispatch_performed: false,
      budget_reserved: false,
      provider_calls_made: false,
      graph_mutated: false,
      handoff_notes: ["runner apply handoff only: ready for a future dispatcher"],
    },
    applied_run_receipt: {
      receipt_id: "midnight-oil-test-applied-run-receipt",
      runner_handoff_id: "midnight-oil-test-runner-handoff",
      approval_receipt_id: "midnight-oil-test-approval-receipt",
      launch_packet_id: "midnight-oil-test-launch-packet",
      run_id: "midnight-oil-test",
      status: "planned_not_dispatched",
      planned_role_count: 2,
      planned_budget_usd: 7.2,
      unallocated_budget_usd: 4.8,
      planned_role_route_receipt_ids: [
        "midnight-oil-test-planner-route-receipt",
        "midnight-oil-test-gatherer-route-receipt",
      ],
      dispatch_performed: false,
      budget_reserved: false,
      provider_calls_made: false,
      retrieval_performed: false,
      graph_mutated: false,
      final_artifact_created: false,
      applied_notes: ["dry applied run receipt only: no autonomous agents dispatched"],
    },
    notes: ["preflight only: no agents launched, no budget reserved, no retrieval performed"],
  })),
  dryRunMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-endpoint-dry-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "planned_not_dispatched",
    planned_role_count: 2,
    planned_budget_usd: 7.2,
    unallocated_budget_usd: 4.8,
    planned_role_route_receipt_ids: [
      "midnight-oil-test-planner-route-receipt",
      "midnight-oil-test-gatherer-route-receipt",
    ],
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    applied_notes: ["endpoint dry run only: no autonomous agents dispatched"],
  })),
  dispatchMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-dispatch-receipt",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_live_dispatch_disabled",
    live_dispatch_requested: true,
    blocker_reason: "live_dispatch_disabled",
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_notes: ["live dispatch gate only: autonomous runner execution is disabled"],
  })),
  activationChecklistMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-activation-checklist",
    dispatch_receipt_id: "midnight-oil-test-dispatch-receipt",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "activation_blocked_controls_missing",
    completed_items: ["blocked dispatch receipt exists"],
    missing_items: [
      "operator live-run activation setting",
      "budget reservation provider",
      "model/provider route executor",
      "final HTML artifact writer",
    ],
    dispatch_allowed: false,
    budget_reservation_allowed: false,
    provider_execution_allowed: false,
    retrieval_allowed: false,
    graph_mutation_allowed: false,
    final_artifact_allowed: false,
    checklist_notes: ["activation checklist only: live execution remains blocked"],
  })),
  budgetReservationMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-budget-reservation",
    activation_checklist_receipt_id: "midnight-oil-test-activation-checklist",
    dispatch_receipt_id: "midnight-oil-test-dispatch-receipt",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_budget_reservation_disabled",
    requested_reservation_usd: 7.2,
    approved_price_ceiling_usd: 12,
    planned_budget_usd: 7.2,
    unallocated_budget_usd: 4.8,
    blocker_reason: "budget_reservation_provider_missing",
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_calls_made: false,
    dispatch_performed: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    reservation_notes: ["budget reservation gate only: reservation provider is not configured"],
  })),
  providerRouteMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-provider-route",
    budget_reservation_receipt_id: "midnight-oil-test-budget-reservation",
    activation_checklist_receipt_id: "midnight-oil-test-activation-checklist",
    dispatch_receipt_id: "midnight-oil-test-dispatch-receipt",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_provider_route_executor_disabled",
    requested_route_count: 2,
    planned_role_route_receipt_ids: [
      "midnight-oil-test-planner-route-receipt",
      "midnight-oil-test-gatherer-route-receipt",
    ],
    blocker_reason: "provider_route_executor_missing",
    route_executor_allowed: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    budget_reserved: false,
    dispatch_performed: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    provider_route_notes: ["provider route gate only: model/provider route executor is not configured"],
  })),
  retrievalMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-retrieval",
    provider_route_receipt_id: "midnight-oil-test-provider-route",
    budget_reservation_receipt_id: "midnight-oil-test-budget-reservation",
    activation_checklist_receipt_id: "midnight-oil-test-activation-checklist",
    dispatch_receipt_id: "midnight-oil-test-dispatch-receipt",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_retrieval_executor_disabled",
    planned_source_policy: ["arxiv", "substack", "operator_corpus"],
    planned_source_receipt_ids: [
      "midnight-oil-test-arxiv-source-receipt",
      "midnight-oil-test-substack-source-receipt",
      "midnight-oil-test-operator_corpus-source-receipt",
    ],
    blocker_reason: "retrieval_executor_missing",
    retrieval_allowed: false,
    source_receipts_created: false,
    retrieval_performed: false,
    provider_calls_made: false,
    budget_reserved: false,
    dispatch_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    retrieval_notes: ["retrieval gate only: retrieval executor and source receipt writer are not configured"],
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
    expect(screen.getAllByText("Dispatch").length).toBeGreaterThan(0);
    expect(screen.getByText("disabled")).toBeTruthy();
    expect(screen.getByText("Approval receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-approval-receipt")).toBeTruthy();
    expect(screen.getByText("Runner apply")).toBeTruthy();
    expect(screen.getAllByText("required").length).toBeGreaterThan(0);
    expect(screen.getByText("Runner handoff")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-handoff")).toBeTruthy();
    expect(screen.getByText("ready for runner apply")).toBeTruthy();
    expect(screen.getByText("not dispatched")).toBeTruthy();
    expect(screen.getByText("Applied run")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-applied-run-receipt")).toBeTruthy();
    expect(screen.getByText("planned not dispatched")).toBeTruthy();
    expect(screen.getByText("not created")).toBeTruthy();
    expect(screen.getByText(/no agents launched/i)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Dry run endpoint" }));

    await waitFor(() => expect(dryRunMidnightOil).toHaveBeenCalled());
    expect(dryRunMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
    });
    expect(screen.getByText("Dry-run receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-endpoint-dry-run-receipt")).toBeTruthy();
    expect(screen.getAllByText("planned not dispatched").length).toBeGreaterThan(1);
    expect(screen.getAllByText("not performed").length).toBeGreaterThan(1);

    await user.click(screen.getByRole("button", { name: "Dispatch gate" }));

    await waitFor(() => expect(dispatchMidnightOil).toHaveBeenCalled());
    expect(dispatchMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      applied_run_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-applied-run-receipt",
      }),
      live_dispatch_requested: true,
    });
    expect(screen.getByText("Dispatch receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-dispatch-receipt")).toBeTruthy();
    expect(screen.getByText("blocked live dispatch disabled")).toBeTruthy();
    expect(screen.getByText("live dispatch disabled")).toBeTruthy();
    expect(screen.getAllByText("none").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Activation checklist" }));

    await waitFor(() => expect(activationChecklistMidnightOil).toHaveBeenCalled());
    expect(activationChecklistMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      applied_run_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-applied-run-receipt",
      }),
      dispatch_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-dispatch-receipt",
      }),
    });
    expect(screen.getByText("Activation receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-activation-checklist")).toBeTruthy();
    expect(screen.getByText("activation blocked controls missing")).toBeTruthy();
    expect(screen.getByText("4 controls")).toBeTruthy();
    expect(screen.getByText("operator live-run activation setting")).toBeTruthy();
    expect(screen.getByText("budget reservation provider")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Budget reservation" }));

    await waitFor(() => expect(budgetReservationMidnightOil).toHaveBeenCalled());
    expect(budgetReservationMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      applied_run_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-applied-run-receipt",
      }),
      dispatch_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-dispatch-receipt",
      }),
      activation_checklist_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-activation-checklist",
      }),
    });
    expect(screen.getByText("Budget receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-budget-reservation")).toBeTruthy();
    expect(screen.getByText("blocked budget reservation disabled")).toBeTruthy();
    expect(screen.getByText("budget reservation provider missing")).toBeTruthy();
    expect(screen.getAllByText("$7.20").length).toBeGreaterThan(1);

    await user.click(screen.getByRole("button", { name: "Provider route" }));

    await waitFor(() => expect(providerRouteMidnightOil).toHaveBeenCalled());
    expect(providerRouteMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      applied_run_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-applied-run-receipt",
      }),
      dispatch_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-dispatch-receipt",
      }),
      activation_checklist_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-activation-checklist",
      }),
      budget_reservation_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-reservation",
      }),
    });
    expect(screen.getByText("Provider receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-provider-route")).toBeTruthy();
    expect(screen.getByText("blocked provider route executor disabled")).toBeTruthy();
    expect(screen.getByText("provider route executor missing")).toBeTruthy();
    expect(screen.getAllByText("none").length).toBeGreaterThan(1);

    await user.click(screen.getByRole("button", { name: "Retrieval" }));

    await waitFor(() => expect(retrievalMidnightOil).toHaveBeenCalled());
    expect(retrievalMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      applied_run_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-applied-run-receipt",
      }),
      dispatch_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-dispatch-receipt",
      }),
      activation_checklist_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-activation-checklist",
      }),
      budget_reservation_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-reservation",
      }),
      provider_route_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-route",
      }),
    });
    expect(screen.getByText("Retrieval receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-retrieval")).toBeTruthy();
    expect(screen.getByText("blocked retrieval executor disabled")).toBeTruthy();
    expect(screen.getByText("retrieval executor missing")).toBeTruthy();
    expect(screen.getAllByText("none").length).toBeGreaterThan(2);
  });
});
