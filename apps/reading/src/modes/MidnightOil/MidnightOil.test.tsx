import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MidnightOil from "./index";
import {
  activationChecklistMidnightOil,
  budgetProviderAdapterPlanMidnightOil,
  budgetReservationMidnightOil,
  controlLedgerAdapterPlanMidnightOil,
  controlLedgerPersistenceApplyPlanMidnightOil,
  controlLedgerPersistencePlanMidnightOil,
  dispatchMidnightOil,
  dryRunMidnightOil,
  finalArtifactAdapterPlanMidnightOil,
  finalArtifactMidnightOil,
  graphAdapterPlanMidnightOil,
  graphMutationMidnightOil,
  liveDispatchFinalEnablementApplyPlanMidnightOil,
  liveDispatchFinalEnablementPlanMidnightOil,
  liveRunActivationSettingsMidnightOil,
  operatorDispatchActivationReadinessPlanMidnightOil,
  operatorDispatchAdapterPlanMidnightOil,
  preflightMidnightOil,
  providerExecutorAdapterPlanMidnightOil,
  providerRouteMidnightOil,
  repositoryTransactionPlanMidnightOil,
  retrievalAdapterPlanMidnightOil,
  retrievalMidnightOil,
  runnerControlPlanMidnightOil,
  runnerDispatchSchedulerPlanMidnightOil,
  runnerDispatchWorkerBootstrapPlanMidnightOil,
  runnerReadinessMidnightOil,
  schedulerLeaseRetryPlanMidnightOil,
  workerQueueClaimPlanMidnightOil,
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
  liveRunActivationSettingsMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-live-run-activation-settings",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_live_run_activation_disabled",
    settings_scope: "midnight_oil_live_run_activation",
    requested_live_run_enabled: true,
    requested_price_ceiling_usd: 12,
    requested_work_minutes: 90,
    approved_price_ceiling_usd: 12,
    approved_work_minutes: 90,
    missing_controls: [
      "operator live-run activation setting persistence",
      "budget reservation provider",
      "model/provider route executor",
      "retrieval executor with source receipts",
      "graph mutation writer",
      "final HTML artifact writer",
    ],
    blocker_reason: "live_run_activation_controls_missing",
    live_run_activation_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    settings_notes: ["live-run activation settings gate only: live execution remains disabled"],
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
    live_run_activation_settings_receipt_id: "midnight-oil-test-live-run-activation-settings",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "activation_blocked_controls_missing",
    completed_items: [
      "blocked live-run activation settings receipt exists",
      "blocked dispatch receipt exists",
    ],
    missing_items: [
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
  graphMutationMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-graph-mutation",
    retrieval_receipt_id: "midnight-oil-test-retrieval",
    provider_route_receipt_id: "midnight-oil-test-provider-route",
    budget_reservation_receipt_id: "midnight-oil-test-budget-reservation",
    activation_checklist_receipt_id: "midnight-oil-test-activation-checklist",
    dispatch_receipt_id: "midnight-oil-test-dispatch-receipt",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_graph_mutation_disabled",
    planned_graph_node_ids: [
      "midnight-oil-test-run-node",
      "midnight-oil-test-arxiv-source-node",
      "midnight-oil-test-substack-source-node",
      "midnight-oil-test-operator_corpus-source-node",
    ],
    planned_graph_edge_ids: [
      "midnight-oil-test-arxiv-source-edge",
      "midnight-oil-test-substack-source-edge",
      "midnight-oil-test-operator_corpus-source-edge",
    ],
    blocker_reason: "graph_mutation_writer_missing",
    graph_mutation_allowed: false,
    graph_mutated: false,
    source_receipts_created: false,
    retrieval_performed: false,
    provider_calls_made: false,
    budget_reserved: false,
    dispatch_performed: false,
    final_artifact_created: false,
    graph_notes: ["graph mutation gate only: graph writer is not configured"],
  })),
  finalArtifactMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-artifact",
    graph_mutation_receipt_id: "midnight-oil-test-graph-mutation",
    retrieval_receipt_id: "midnight-oil-test-retrieval",
    provider_route_receipt_id: "midnight-oil-test-provider-route",
    budget_reservation_receipt_id: "midnight-oil-test-budget-reservation",
    activation_checklist_receipt_id: "midnight-oil-test-activation-checklist",
    dispatch_receipt_id: "midnight-oil-test-dispatch-receipt",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_final_artifact_writer_disabled",
    planned_artifact_id: "midnight-oil-test-html-research-asset",
    planned_twin_note_document_id: "midnight-oil-test-twin-note-document",
    final_format: "html",
    pdf_allowed: false,
    blocker_reason: "final_html_artifact_writer_missing",
    final_artifact_allowed: false,
    final_artifact_created: false,
    graph_mutated: false,
    source_receipts_created: false,
    retrieval_performed: false,
    provider_calls_made: false,
    budget_reserved: false,
    dispatch_performed: false,
    artifact_notes: ["final artifact gate only: final HTML artifact writer is not configured"],
  })),
  runnerReadinessMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-runner-readiness",
    final_artifact_receipt_id: "midnight-oil-test-final-artifact",
    graph_mutation_receipt_id: "midnight-oil-test-graph-mutation",
    retrieval_receipt_id: "midnight-oil-test-retrieval",
    provider_route_receipt_id: "midnight-oil-test-provider-route",
    budget_reservation_receipt_id: "midnight-oil-test-budget-reservation",
    activation_checklist_receipt_id: "midnight-oil-test-activation-checklist",
    live_run_activation_settings_receipt_id: "midnight-oil-test-live-run-activation-settings",
    dispatch_receipt_id: "midnight-oil-test-dispatch-receipt",
    applied_run_receipt_id: "midnight-oil-test-applied-run-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_runner_readiness_controls_missing",
    completed_receipt_ids: [
      "midnight-oil-test-launch-packet",
      "midnight-oil-test-approval-receipt",
      "midnight-oil-test-runner-handoff",
      "midnight-oil-test-applied-run-receipt",
      "midnight-oil-test-live-run-activation-settings",
      "midnight-oil-test-dispatch-receipt",
      "midnight-oil-test-activation-checklist",
      "midnight-oil-test-budget-reservation",
      "midnight-oil-test-provider-route",
      "midnight-oil-test-retrieval",
      "midnight-oil-test-graph-mutation",
      "midnight-oil-test-final-artifact",
    ],
    remaining_blockers: [
      "budget reservation provider",
      "model/provider route executor",
      "retrieval executor with source receipts",
      "graph mutation writer",
      "final HTML artifact writer",
      "operator live-run dispatch enablement",
    ],
    blocker_reason: "runner_readiness_controls_missing",
    live_run_allowed: false,
    dispatch_allowed: false,
    budget_reservation_allowed: false,
    provider_execution_allowed: false,
    retrieval_allowed: false,
    graph_mutation_allowed: false,
    final_artifact_allowed: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    readiness_notes: ["runner readiness gate only: full no-spend receipt chain has been reviewed"],
  })),
  runnerControlPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_runner_controls_unimplemented",
    requested_control_scope: [
      "budget_reservation_provider",
      "model_provider_route_executor",
      "retrieval_executor_source_receipts",
      "graph_mutation_writer",
      "final_html_artifact_writer",
      "operator_live_dispatch_enablement",
    ],
    required_control_order: [
      "budget_reservation_provider",
      "model_provider_route_executor",
      "retrieval_executor_source_receipts",
      "graph_mutation_writer",
      "final_html_artifact_writer",
      "operator_live_dispatch_enablement",
    ],
    implementation_requirements: [
      {
        control_key: "budget_reservation_provider",
        blocker: "budget reservation provider",
        required_artifact: "Budget reservation provider with idempotent no-overrun holds.",
        implementation_status: "missing",
        live_enablement_allowed: false,
      },
      {
        control_key: "model_provider_route_executor",
        blocker: "model/provider route executor",
        required_artifact: "Provider route executor that records route receipts before calls.",
        implementation_status: "missing",
        live_enablement_allowed: false,
      },
      {
        control_key: "retrieval_executor_source_receipts",
        blocker: "retrieval executor with source receipts",
        required_artifact: "Retrieval executor that emits source receipts for every source.",
        implementation_status: "missing",
        live_enablement_allowed: false,
      },
    ],
    remaining_blockers: [
      "budget reservation provider",
      "model/provider route executor",
      "retrieval executor with source receipts",
    ],
    blocker_reason: "runner_controls_unimplemented",
    live_run_allowed: false,
    dispatch_allowed: false,
    budget_reservation_allowed: false,
    provider_execution_allowed: false,
    retrieval_allowed: false,
    graph_mutation_allowed: false,
    final_artifact_allowed: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    control_plan_notes: ["runner control plan only: implementation requirements recorded"],
  })),
  budgetProviderAdapterPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_budget_provider_adapter_unimplemented",
    adapter_key: "budget_reservation_provider",
    planned_adapter_id: "midnight-oil-test-budget-provider-adapter",
    planned_ledger_id: "midnight-oil-test-budget-reservation-ledger",
    idempotency_key:
      "midnight-oil-test-launch-packet:midnight-oil-test-approval-receipt:budget_reservation_provider",
    approved_price_ceiling_usd: 12,
    planned_budget_usd: 7.2,
    unallocated_budget_usd: 4.8,
    required_invariants: [
      "adapter must reject reservations above the approved price ceiling",
      "adapter must be idempotent for the same launch packet and approval receipt",
      "adapter must write a durable ledger row before any provider execution can proceed",
    ],
    required_ledger_fields: [
      "reservation_id",
      "run_id",
      "launch_packet_id",
      "approval_receipt_id",
      "approved_price_ceiling_usd",
      "planned_budget_usd",
      "reserved_budget_usd",
      "idempotency_key",
      "status",
      "created_at",
      "released_at",
    ],
    blocker_reason: "budget_provider_adapter_unimplemented",
    budget_reservation_allowed: false,
    budget_reserved: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    provider_execution_allowed: false,
    retrieval_allowed: false,
    graph_mutation_allowed: false,
    final_artifact_allowed: false,
    dispatch_performed: false,
    provider_calls_made: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    adapter_plan_notes: ["budget provider adapter plan only: no reservation provider is configured"],
  })),
  providerExecutorAdapterPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    budget_provider_adapter_plan_receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_provider_executor_adapter_unimplemented",
    adapter_key: "model_provider_route_executor",
    planned_executor_id: "midnight-oil-test-provider-executor-adapter",
    planned_route_ledger_id: "midnight-oil-test-provider-route-ledger",
    planned_role_route_receipt_ids: [
      "midnight-oil-test-planner-route-receipt",
      "midnight-oil-test-gatherer-route-receipt",
    ],
    requested_route_count: 2,
    route_mode: "auto_cost",
    provider_policy: "operator_configured_models_only",
    required_invariants: [
      "executor must require an active budget reservation before any provider call",
      "executor must create a route receipt for every planned role before execution",
      "executor must enforce the operator-approved route mode and source policy",
    ],
    required_route_receipt_fields: [
      "route_receipt_id",
      "run_id",
      "role",
      "route_mode",
      "provider",
      "model",
      "estimated_cost_usd",
      "budget_reservation_id",
      "fallback_chain",
      "created_at",
    ],
    blocker_reason: "provider_executor_adapter_unimplemented",
    provider_execution_allowed: false,
    provider_calls_made: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    retrieval_allowed: false,
    graph_mutation_allowed: false,
    final_artifact_allowed: false,
    dispatch_performed: false,
    retrieval_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    adapter_plan_notes: ["provider executor adapter plan only: no model/provider executor is configured"],
  })),
  retrievalAdapterPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-retrieval-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    budget_provider_adapter_plan_receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
    provider_executor_adapter_plan_receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_retrieval_adapter_unimplemented",
    adapter_key: "retrieval_executor_source_receipts",
    planned_executor_id: "midnight-oil-test-retrieval-adapter",
    planned_source_ledger_id: "midnight-oil-test-source-receipt-ledger",
    planned_source_policy: ["arxiv", "substack", "operator_corpus"],
    planned_source_receipt_ids: [
      "midnight-oil-test-arxiv-source-receipt",
      "midnight-oil-test-substack-source-receipt",
      "midnight-oil-test-operator_corpus-source-receipt",
    ],
    requested_source_count: 3,
    required_invariants: [
      "retrieval adapter must require provider route receipts before source access",
      "retrieval adapter must create a source receipt for every approved source policy entry",
      "retrieval adapter must preserve source URL, title, author, retrieval time, and license metadata",
    ],
    required_source_receipt_fields: [
      "source_receipt_id",
      "run_id",
      "source_policy",
      "source_uri",
      "title",
      "author",
      "retrieved_at",
      "license",
      "content_digest",
      "availability_status",
    ],
    blocker_reason: "retrieval_adapter_unimplemented",
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    graph_mutation_allowed: false,
    final_artifact_allowed: false,
    dispatch_performed: false,
    graph_mutated: false,
    final_artifact_created: false,
    adapter_plan_notes: ["retrieval adapter plan only: no source connector is configured"],
  })),
  graphAdapterPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-graph-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    budget_provider_adapter_plan_receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
    provider_executor_adapter_plan_receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
    retrieval_adapter_plan_receipt_id: "midnight-oil-test-retrieval-adapter-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_graph_adapter_unimplemented",
    adapter_key: "graph_mutation_writer",
    planned_writer_id: "midnight-oil-test-graph-adapter",
    planned_graph_ledger_id: "midnight-oil-test-graph-mutation-ledger",
    planned_graph_node_ids: [
      "midnight-oil-test-run-node",
      "midnight-oil-test-arxiv-source-node",
      "midnight-oil-test-substack-source-node",
      "midnight-oil-test-operator_corpus-source-node",
    ],
    planned_graph_edge_ids: [
      "midnight-oil-test-arxiv-cites-edge",
      "midnight-oil-test-substack-cites-edge",
      "midnight-oil-test-operator_corpus-cites-edge",
    ],
    required_invariants: [
      "graph adapter must require source receipts before any graph write",
      "graph adapter must write idempotent nodes and edges keyed by run and source receipt",
      "graph adapter must preserve provenance links to route and source receipts",
    ],
    required_graph_receipt_fields: [
      "graph_receipt_id",
      "run_id",
      "node_ids",
      "edge_ids",
      "source_receipt_ids",
      "route_receipt_ids",
      "content_digest",
      "idempotency_key",
      "created_at",
    ],
    blocker_reason: "graph_adapter_unimplemented",
    graph_mutation_allowed: false,
    graph_mutated: false,
    source_receipts_created: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    final_artifact_allowed: false,
    dispatch_performed: false,
    final_artifact_created: false,
    adapter_plan_notes: ["graph adapter plan only: no graph writer is configured"],
  })),
  finalArtifactAdapterPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    budget_provider_adapter_plan_receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
    provider_executor_adapter_plan_receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
    retrieval_adapter_plan_receipt_id: "midnight-oil-test-retrieval-adapter-plan",
    graph_adapter_plan_receipt_id: "midnight-oil-test-graph-adapter-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_final_artifact_adapter_unimplemented",
    adapter_key: "final_html_artifact_writer",
    planned_writer_id: "midnight-oil-test-final-html-artifact-writer",
    planned_artifact_ledger_id: "midnight-oil-test-artifact-receipt-ledger",
    planned_artifact_id: "midnight-oil-test-html-research-asset",
    planned_twin_note_document_id: "midnight-oil-test-twin-note-document",
    final_format: "html",
    pdf_allowed: false,
    required_invariants: [
      "final artifact adapter must require route, source, and graph receipts before writing HTML",
      "final artifact adapter must create an Antiek information asset and twin-note document atomically",
      "final artifact adapter must preserve provenance links to launch, approval, route, source, and graph receipts",
    ],
    required_artifact_receipt_fields: [
      "artifact_receipt_id",
      "run_id",
      "artifact_id",
      "twin_note_document_id",
      "final_format",
      "route_receipt_ids",
      "source_receipt_ids",
      "graph_receipt_id",
      "content_digest",
      "created_at",
    ],
    blocker_reason: "final_artifact_adapter_unimplemented",
    final_artifact_allowed: false,
    final_artifact_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    source_receipts_created: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    dispatch_performed: false,
    adapter_plan_notes: ["final artifact adapter plan only: no HTML asset writer is configured"],
  })),
  operatorDispatchAdapterPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    budget_provider_adapter_plan_receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
    provider_executor_adapter_plan_receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
    retrieval_adapter_plan_receipt_id: "midnight-oil-test-retrieval-adapter-plan",
    graph_adapter_plan_receipt_id: "midnight-oil-test-graph-adapter-plan",
    final_artifact_adapter_plan_receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_operator_dispatch_adapter_unimplemented",
    adapter_key: "operator_live_dispatch_enablement",
    planned_setting_id: "midnight-oil-test-operator-live-dispatch-setting",
    planned_control_ledger_id: "midnight-oil-test-operator-dispatch-control-ledger",
    required_invariants: [
      "operator dispatch adapter must require every implementation adapter plan before live enablement",
      "operator dispatch adapter must require an explicit operator toggle for the approved run id",
      "operator dispatch adapter must write a durable control ledger row before live dispatch",
    ],
    required_dispatch_enablement_fields: [
      "operator_dispatch_setting_id",
      "run_id",
      "approval_receipt_id",
      "approved_price_ceiling_usd",
      "approved_work_minutes",
      "enabled_by_operator_id",
      "enabled_at",
      "expires_at",
      "idempotency_key",
      "rollback_receipt_id",
    ],
    blocker_reason: "operator_dispatch_adapter_unimplemented",
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: ["operator dispatch adapter plan only: live dispatch remains disabled"],
  })),
  controlLedgerAdapterPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
    operator_dispatch_adapter_plan_receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    budget_provider_adapter_plan_receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
    provider_executor_adapter_plan_receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
    retrieval_adapter_plan_receipt_id: "midnight-oil-test-retrieval-adapter-plan",
    graph_adapter_plan_receipt_id: "midnight-oil-test-graph-adapter-plan",
    final_artifact_adapter_plan_receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_control_ledger_adapter_unimplemented",
    adapter_key: "operator_dispatch_control_ledger",
    planned_setting_id: "midnight-oil-test-operator-live-dispatch-setting",
    planned_control_ledger_id: "midnight-oil-test-operator-dispatch-control-ledger",
    planned_audit_log_id: "midnight-oil-test-operator-dispatch-audit-log",
    planned_rollback_receipt_id: "midnight-oil-test-operator-dispatch-rollback-receipt",
    required_invariants: [
      "control ledger adapter must persist exactly one enablement row per approved run id and idempotency key",
      "control ledger adapter must bind the row to the launch packet, approval receipt, and operator setting",
      "control ledger adapter must write an audit log row and rollback receipt before live dispatch can be enabled",
    ],
    required_control_ledger_fields: [
      "control_ledger_id",
      "operator_dispatch_setting_id",
      "run_id",
      "launch_packet_id",
      "approval_receipt_id",
      "approved_price_ceiling_usd",
      "approved_work_minutes",
      "enabled_by_operator_id",
      "enabled_at",
      "expires_at",
      "idempotency_key",
      "audit_log_id",
      "rollback_receipt_id",
      "created_at",
    ],
    required_rollback_receipt_fields: [
      "rollback_receipt_id",
      "control_ledger_id",
      "operator_dispatch_setting_id",
      "run_id",
      "previous_enabled_state",
      "rollback_reason",
      "rolled_back_by_operator_id",
      "rolled_back_at",
    ],
    blocker_reason: "control_ledger_adapter_unimplemented",
    control_ledger_persistence_allowed: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: ["control ledger adapter plan only: no ledger row is persisted"],
  })),
  controlLedgerPersistencePlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
    control_ledger_adapter_plan_receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
    operator_dispatch_adapter_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_control_ledger_persistence_unimplemented",
    adapter_key: "operator_dispatch_control_ledger_persistence",
    planned_repository_id: "midnight-oil-test-operator-dispatch-control-repository",
    planned_transaction_id: "midnight-oil-test-operator-dispatch-control-transaction",
    planned_setting_id: "midnight-oil-test-operator-live-dispatch-setting",
    planned_control_ledger_id: "midnight-oil-test-operator-dispatch-control-ledger",
    planned_audit_log_id: "midnight-oil-test-operator-dispatch-audit-log",
    planned_rollback_receipt_id: "midnight-oil-test-operator-dispatch-rollback-receipt",
    required_storage_tables: [
      "operator_dispatch_settings",
      "operator_dispatch_control_ledger",
      "operator_dispatch_audit_log",
      "operator_dispatch_rollback_receipts",
    ],
    required_transaction_invariants: [
      "control ledger persistence must commit setting, ledger, audit log, and rollback receipt atomically",
      "control ledger persistence must reject duplicate enablement rows for the same run id and idempotency key",
      "control ledger persistence must leave live dispatch disabled until the committed receipt is verified",
    ],
    required_apply_fields: [
      "operator_dispatch_setting_id",
      "control_ledger_id",
      "audit_log_id",
      "rollback_receipt_id",
      "transaction_id",
      "committed_at",
    ],
    blocker_reason: "control_ledger_persistence_unimplemented",
    persistence_adapter_allowed: false,
    control_ledger_persistence_allowed: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "control ledger persistence plan only: no repository transaction is opened",
    ],
  })),
  controlLedgerPersistenceApplyPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
    control_ledger_persistence_plan_receipt_id:
      "midnight-oil-test-control-ledger-persistence-plan",
    control_ledger_adapter_plan_receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
    operator_dispatch_adapter_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_control_ledger_persistence_apply_unimplemented",
    adapter_key: "operator_dispatch_control_ledger_persistence_apply",
    planned_repository_id: "midnight-oil-test-operator-dispatch-control-repository",
    planned_transaction_id: "midnight-oil-test-operator-dispatch-control-transaction",
    planned_commit_receipt_id: "midnight-oil-test-operator-dispatch-control-commit-receipt",
    planned_content_digest:
      "midnight-oil-test-operator-dispatch-control-persistence-content-digest",
    planned_setting_id: "midnight-oil-test-operator-live-dispatch-setting",
    planned_control_ledger_id: "midnight-oil-test-operator-dispatch-control-ledger",
    planned_audit_log_id: "midnight-oil-test-operator-dispatch-audit-log",
    planned_rollback_receipt_id: "midnight-oil-test-operator-dispatch-rollback-receipt",
    required_commit_invariants: [
      "apply planner must require the persistence implementation plan before any transaction is opened",
      "apply planner must keep the transaction closed until a real repository adapter exists",
      "apply planner must require a commit receipt before operator live dispatch can be enabled",
    ],
    required_commit_receipt_fields: [
      "commit_receipt_id",
      "repository_id",
      "transaction_id",
      "operator_dispatch_setting_id",
      "control_ledger_id",
      "audit_log_id",
      "rollback_receipt_id",
      "content_digest",
      "transaction_opened",
      "transaction_committed",
    ],
    blocker_reason: "control_ledger_persistence_apply_unimplemented",
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_persistence_allowed: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "control ledger persistence apply plan only: no repository transaction is opened or committed",
    ],
  })),
  operatorDispatchActivationReadinessPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-operator-dispatch-activation-readiness-plan",
    control_ledger_persistence_apply_plan_receipt_id:
      "midnight-oil-test-control-ledger-persistence-apply-plan",
    control_ledger_persistence_plan_receipt_id:
      "midnight-oil-test-control-ledger-persistence-plan",
    control_ledger_adapter_plan_receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
    operator_dispatch_adapter_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_operator_dispatch_activation_readiness_unimplemented",
    adapter_key: "operator_dispatch_activation_readiness",
    planned_commit_receipt_id: "midnight-oil-test-operator-dispatch-control-commit-receipt",
    planned_activation_readiness_receipt_id:
      "midnight-oil-test-operator-dispatch-activation-readiness-receipt",
    planned_dispatch_enablement_id:
      "midnight-oil-test-operator-dispatch-live-enable-activation",
    planned_repository_id: "midnight-oil-test-operator-dispatch-control-repository",
    planned_transaction_id: "midnight-oil-test-operator-dispatch-control-transaction",
    required_activation_invariants: [
      "activation readiness must require a committed control ledger persistence receipt before live dispatch can be enabled",
      "activation readiness must verify operator approval scope, price ceiling, work minutes, and expiry before enablement",
      "activation readiness must keep live dispatch disabled until budget, provider, retrieval, graph, and artifact adapters are implemented",
    ],
    required_activation_receipt_fields: [
      "activation_readiness_receipt_id",
      "run_id",
      "launch_packet_id",
      "approval_receipt_id",
      "commit_receipt_id",
      "operator_dispatch_setting_id",
      "readiness_blockers",
      "activation_ready",
      "operator_live_dispatch_enabled",
    ],
    readiness_blockers: [
      "committed control ledger persistence receipt",
      "operator activation receipt writer",
      "budget reservation provider",
      "model/provider route executor",
      "retrieval executor with source receipts",
      "graph mutation writer",
      "final HTML artifact writer",
    ],
    blocker_reason: "operator_dispatch_activation_readiness_unimplemented",
    activation_readiness_allowed: false,
    activation_ready: false,
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "operator dispatch activation readiness plan only: no live dispatch readiness is granted",
    ],
  })),
  liveDispatchFinalEnablementPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-live-dispatch-final-enablement-plan",
    operator_dispatch_activation_readiness_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-activation-readiness-plan",
    control_ledger_persistence_apply_plan_receipt_id:
      "midnight-oil-test-control-ledger-persistence-apply-plan",
    control_ledger_persistence_plan_receipt_id:
      "midnight-oil-test-control-ledger-persistence-plan",
    control_ledger_adapter_plan_receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
    operator_dispatch_adapter_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_live_dispatch_final_enablement_unimplemented",
    adapter_key: "live_dispatch_final_enablement",
    planned_activation_readiness_receipt_id:
      "midnight-oil-test-operator-dispatch-activation-readiness-receipt",
    planned_dispatch_enablement_id:
      "midnight-oil-test-operator-dispatch-live-enable-activation",
    planned_live_dispatch_receipt_id: "midnight-oil-test-live-dispatch-final-enable-receipt",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    readiness_blockers: [
      "committed control ledger persistence receipt",
      "operator activation receipt writer",
      "live dispatch final enablement implementation",
    ],
    required_enablement_invariants: [
      "final enablement must require an activation readiness receipt that is activation_ready before live dispatch can be enabled",
      "final enablement must require the committed control ledger receipt and operator activation receipt before any dispatch",
    ],
    required_enablement_receipt_fields: [
      "live_dispatch_receipt_id",
      "runner_dispatch_id",
      "run_id",
      "launch_packet_id",
      "approval_receipt_id",
      "activation_readiness_receipt_id",
      "dispatch_enablement_id",
      "live_dispatch_enabled",
      "live_dispatch_ready",
      "dispatch_performed",
    ],
    blocker_reason: "live_dispatch_final_enablement_unimplemented",
    final_enablement_allowed: false,
    live_dispatch_enabled: false,
    live_dispatch_ready: false,
    activation_readiness_allowed: false,
    activation_ready: false,
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "live dispatch final enablement plan only: no enablement is granted and no runner dispatch is created",
    ],
  })),
  liveDispatchFinalEnablementApplyPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
    live_dispatch_final_enablement_plan_receipt_id:
      "midnight-oil-test-live-dispatch-final-enablement-plan",
    operator_dispatch_activation_readiness_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-activation-readiness-plan",
    control_ledger_persistence_apply_plan_receipt_id:
      "midnight-oil-test-control-ledger-persistence-apply-plan",
    control_ledger_persistence_plan_receipt_id:
      "midnight-oil-test-control-ledger-persistence-plan",
    control_ledger_adapter_plan_receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
    operator_dispatch_adapter_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-adapter-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_live_dispatch_final_enablement_apply_unimplemented",
    adapter_key: "live_dispatch_final_enablement_apply",
    planned_activation_readiness_receipt_id:
      "midnight-oil-test-operator-dispatch-activation-readiness-receipt",
    planned_dispatch_enablement_id:
      "midnight-oil-test-operator-dispatch-live-enable-activation",
    planned_live_dispatch_receipt_id: "midnight-oil-test-live-dispatch-final-enable-receipt",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_apply_receipt_id: "midnight-oil-test-live-dispatch-final-enable-apply-receipt",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    planned_repository_id: "midnight-oil-test-operator-dispatch-control-repository",
    planned_transaction_id: "midnight-oil-test-live-dispatch-final-enable-transaction",
    apply_blockers: [
      "activation-ready receipt implementation",
      "final enablement apply receipt writer",
      "dispatch idempotency repository",
      "runner dispatch scheduler",
    ],
    required_apply_invariants: [
      "apply planner must require an activation-ready receipt before any final enablement transaction is opened",
      "apply planner must use an idempotency key before creating a live dispatch receipt or runner dispatch id",
    ],
    required_apply_receipt_fields: [
      "apply_receipt_id",
      "live_dispatch_receipt_id",
      "runner_dispatch_id",
      "repository_id",
      "transaction_id",
      "idempotency_key",
      "dispatch_performed",
    ],
    blocker_reason: "live_dispatch_final_enablement_apply_unimplemented",
    final_enablement_apply_allowed: false,
    final_enablement_allowed: false,
    live_dispatch_enabled: false,
    live_dispatch_ready: false,
    activation_readiness_allowed: false,
    activation_ready: false,
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "live dispatch final enablement apply plan only: no transaction is opened and no dispatch id is consumed",
    ],
  })),
  runnerDispatchSchedulerPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-runner-dispatch-scheduler-plan",
    live_dispatch_final_enablement_apply_plan_receipt_id:
      "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
    live_dispatch_final_enablement_plan_receipt_id:
      "midnight-oil-test-live-dispatch-final-enablement-plan",
    operator_dispatch_activation_readiness_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-activation-readiness-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_runner_dispatch_scheduler_unimplemented",
    adapter_key: "runner_dispatch_scheduler",
    planned_scheduler_job_id: "midnight-oil-test-runner-dispatch-scheduler-job",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_live_dispatch_receipt_id: "midnight-oil-test-live-dispatch-final-enable-receipt",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    planned_apply_receipt_id: "midnight-oil-test-live-dispatch-final-enable-apply-receipt",
    scheduler_blockers: [
      "durable runner dispatch queue",
      "scheduler lease and retry policy",
      "runner dispatch worker implementation",
    ],
    required_scheduler_invariants: [
      "scheduler planner must require a final enablement apply receipt before any scheduler job is created",
      "scheduler planner must use the final enablement idempotency key before enqueueing a runner dispatch",
    ],
    required_scheduler_receipt_fields: [
      "scheduler_receipt_id",
      "scheduler_job_id",
      "queue_id",
      "runner_dispatch_id",
      "live_dispatch_receipt_id",
      "idempotency_key",
      "dispatch_performed",
    ],
    blocker_reason: "runner_dispatch_scheduler_unimplemented",
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    final_enablement_apply_allowed: false,
    final_enablement_allowed: false,
    live_dispatch_enabled: false,
    live_dispatch_ready: false,
    activation_readiness_allowed: false,
    activation_ready: false,
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "runner dispatch scheduler plan only: no scheduler job is created and no runner dispatch is enqueued",
    ],
  })),
  runnerDispatchWorkerBootstrapPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    live_dispatch_final_enablement_apply_plan_receipt_id:
      "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
    live_dispatch_final_enablement_plan_receipt_id:
      "midnight-oil-test-live-dispatch-final-enablement-plan",
    operator_dispatch_activation_readiness_plan_receipt_id:
      "midnight-oil-test-operator-dispatch-activation-readiness-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_runner_dispatch_worker_bootstrap_unimplemented",
    adapter_key: "runner_dispatch_worker_bootstrap",
    planned_worker_bootstrap_id: "midnight-oil-test-runner-dispatch-worker-bootstrap",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_retry_policy_id: "midnight-oil-test-runner-dispatch-retry-policy",
    planned_dead_letter_queue_id:
      "midnight-oil-test-runner-dispatch-dead-letter-queue",
    planned_scheduler_job_id: "midnight-oil-test-runner-dispatch-scheduler-job",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_live_dispatch_receipt_id: "midnight-oil-test-live-dispatch-final-enable-receipt",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    worker_bootstrap_blockers: [
      "runner dispatch worker runtime",
      "worker lease heartbeat store",
      "retry and dead-letter queue implementation",
      "live dispatch receipt writer",
    ],
    required_worker_invariants: [
      "worker bootstrap planner must require a runner dispatch scheduler plan before any worker is created",
      "worker bootstrap planner must define retry, dead-letter, and idempotency behavior before any runner dispatch is enqueued",
    ],
    required_worker_receipt_fields: [
      "worker_bootstrap_receipt_id",
      "worker_bootstrap_id",
      "worker_id",
      "worker_lease_id",
      "retry_policy_id",
      "dead_letter_queue_id",
      "scheduler_plan_receipt_id",
      "scheduler_job_id",
      "queue_id",
      "runner_dispatch_id",
      "live_dispatch_receipt_id",
      "idempotency_key",
      "worker_started",
      "runner_dispatch_enqueued",
      "dispatch_performed",
    ],
    blocker_reason: "runner_dispatch_worker_bootstrap_unimplemented",
    worker_bootstrap_allowed: false,
    worker_bootstrap_created: false,
    worker_started: false,
    lease_policy_created: false,
    retry_policy_created: false,
    dead_letter_queue_created: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    final_enablement_apply_allowed: false,
    final_enablement_allowed: false,
    live_dispatch_enabled: false,
    live_dispatch_ready: false,
    activation_readiness_allowed: false,
    activation_ready: false,
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "runner dispatch worker bootstrap plan only: no worker is created, no scheduler job is created, and no runner dispatch is enqueued",
    ],
  })),
  schedulerLeaseRetryPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    live_dispatch_final_enablement_apply_plan_receipt_id:
      "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_scheduler_lease_retry_unimplemented",
    adapter_key: "scheduler_lease_retry",
    planned_lease_policy_id: "midnight-oil-test-scheduler-lease-policy",
    planned_retry_policy_id: "midnight-oil-test-runner-dispatch-retry-policy",
    planned_dead_letter_queue_id:
      "midnight-oil-test-runner-dispatch-dead-letter-queue",
    planned_visibility_timeout_seconds: 900,
    planned_lease_ttl_seconds: 300,
    planned_heartbeat_interval_seconds: 60,
    planned_max_attempts: 3,
    planned_backoff_policy: "exponential_jitter",
    planned_scheduler_job_id: "midnight-oil-test-runner-dispatch-scheduler-job",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_live_dispatch_receipt_id: "midnight-oil-test-live-dispatch-final-enable-receipt",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    lease_retry_blockers: [
      "lease policy persistence",
      "retry backoff executor",
      "dead-letter queue persistence",
      "worker heartbeat monitor",
    ],
    required_lease_retry_invariants: [
      "lease retry planner must require a worker bootstrap plan before any lease policy is created",
      "lease retry planner must keep retry and dead-letter policies disabled until a worker can claim the queue transactionally",
    ],
    required_lease_retry_receipt_fields: [
      "lease_policy_id",
      "retry_policy_id",
      "dead_letter_queue_id",
      "visibility_timeout_seconds",
      "lease_ttl_seconds",
      "heartbeat_interval_seconds",
      "max_attempts",
      "backoff_policy",
      "worker_bootstrap_plan_receipt_id",
      "worker_lease_id",
      "runner_dispatch_id",
      "live_dispatch_receipt_id",
      "idempotency_key",
    ],
    blocker_reason: "scheduler_lease_retry_unimplemented",
    lease_retry_allowed: false,
    lease_policy_created: false,
    retry_policy_created: false,
    dead_letter_queue_created: false,
    worker_bootstrap_allowed: false,
    worker_bootstrap_created: false,
    worker_started: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    final_enablement_apply_allowed: false,
    final_enablement_allowed: false,
    live_dispatch_enabled: false,
    live_dispatch_ready: false,
    activation_readiness_allowed: false,
    activation_ready: false,
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "scheduler lease retry plan only: no lease policy, retry policy, dead-letter queue, worker runtime, scheduler job, or runner dispatch is created",
    ],
  })),
  workerQueueClaimPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-worker-queue-claim-plan",
    scheduler_lease_retry_plan_receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    live_dispatch_final_enablement_apply_plan_receipt_id:
      "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_worker_queue_claim_unimplemented",
    adapter_key: "worker_queue_claim",
    planned_queue_claim_id: "midnight-oil-test-worker-queue-claim",
    planned_claim_transaction_id: "midnight-oil-test-worker-queue-claim-transaction",
    planned_claim_lease_token_id: "midnight-oil-test-worker-queue-claim-lease-token",
    planned_claim_cursor_id: "midnight-oil-test-worker-queue-claim-cursor",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_scheduler_job_id: "midnight-oil-test-runner-dispatch-scheduler-job",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_live_dispatch_receipt_id: "midnight-oil-test-live-dispatch-final-enable-receipt",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    planned_visibility_timeout_seconds: 900,
    planned_lease_ttl_seconds: 300,
    planned_heartbeat_interval_seconds: 60,
    planned_max_attempts: 3,
    planned_backoff_policy: "exponential_jitter",
    queue_claim_blockers: [
      "atomic queue claim repository transaction",
      "claim lease token persistence",
      "claim cursor persistence",
      "claim visibility deadline monitor",
    ],
    required_queue_claim_invariants: [
      "worker queue claim planner must require scheduler lease retry planning before any queue item can be claimed",
      "worker queue claim planner must claim one runner dispatch idempotently for a single worker lease token",
    ],
    required_queue_claim_receipt_fields: [
      "worker_queue_claim_receipt_id",
      "scheduler_lease_retry_plan_receipt_id",
      "queue_claim_id",
      "claim_transaction_id",
      "claim_lease_token_id",
      "claim_cursor_id",
      "queue_id",
      "worker_id",
      "worker_lease_id",
      "runner_dispatch_id",
      "idempotency_key",
      "queue_claim_created",
      "claim_transaction_committed",
    ],
    blocker_reason: "worker_queue_claim_unimplemented",
    queue_claim_allowed: false,
    queue_claim_created: false,
    claim_transaction_opened: false,
    claim_transaction_committed: false,
    lease_retry_allowed: false,
    lease_policy_created: false,
    retry_policy_created: false,
    dead_letter_queue_created: false,
    worker_bootstrap_allowed: false,
    worker_bootstrap_created: false,
    worker_started: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    final_enablement_apply_allowed: false,
    final_enablement_allowed: false,
    live_dispatch_enabled: false,
    live_dispatch_ready: false,
    activation_readiness_allowed: false,
    activation_ready: false,
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "worker queue claim plan only: no queue claim, claim transaction, worker runtime, scheduler job, or runner dispatch is created",
    ],
  })),
  repositoryTransactionPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-repository-transaction-plan",
    worker_queue_claim_plan_receipt_id: "midnight-oil-test-worker-queue-claim-plan",
    scheduler_lease_retry_plan_receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    live_dispatch_final_enablement_apply_plan_receipt_id:
      "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_repository_transaction_unimplemented",
    adapter_key: "repository_transaction",
    planned_repository_transaction_id: "midnight-oil-test-repository-transaction",
    planned_transaction_scope: "worker_queue_claim_commit",
    planned_write_set_id: "midnight-oil-test-repository-transaction-write-set",
    planned_lock_id: "midnight-oil-test-repository-transaction-lock",
    planned_commit_receipt_id: "midnight-oil-test-repository-transaction-commit-receipt",
    planned_rollback_receipt_id: "midnight-oil-test-repository-transaction-rollback-receipt",
    planned_queue_claim_id: "midnight-oil-test-worker-queue-claim",
    planned_claim_transaction_id: "midnight-oil-test-worker-queue-claim-transaction",
    planned_claim_lease_token_id: "midnight-oil-test-worker-queue-claim-lease-token",
    planned_claim_cursor_id: "midnight-oil-test-worker-queue-claim-cursor",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_live_dispatch_receipt_id: "midnight-oil-test-live-dispatch-final-enable-receipt",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    repository_transaction_blockers: [
      "repository transaction adapter implementation",
      "claim write-set durability",
      "commit receipt writer",
      "rollback receipt writer",
    ],
    required_repository_transaction_invariants: [
      "repository transaction planner must require worker queue-claim planning before any queue claim can be committed",
      "repository transaction planner must emit commit and rollback receipt ids before execution is enabled",
    ],
    required_repository_transaction_receipt_fields: [
      "repository_transaction_receipt_id",
      "worker_queue_claim_plan_receipt_id",
      "repository_transaction_id",
      "write_set_id",
      "lock_id",
      "commit_receipt_id",
      "rollback_receipt_id",
      "queue_claim_id",
      "claim_transaction_id",
      "idempotency_key",
      "repository_transaction_committed",
    ],
    blocker_reason: "repository_transaction_unimplemented",
    repository_transaction_allowed: false,
    repository_transaction_opened: false,
    repository_transaction_committed: false,
    queue_claim_allowed: false,
    queue_claim_created: false,
    claim_transaction_opened: false,
    claim_transaction_committed: false,
    lease_retry_allowed: false,
    lease_policy_created: false,
    retry_policy_created: false,
    dead_letter_queue_created: false,
    worker_bootstrap_allowed: false,
    worker_bootstrap_created: false,
    worker_started: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    final_enablement_apply_allowed: false,
    final_enablement_allowed: false,
    live_dispatch_enabled: false,
    live_dispatch_ready: false,
    activation_readiness_allowed: false,
    activation_ready: false,
    transaction_opened: false,
    transaction_committed: false,
    setting_persisted: false,
    control_ledger_written: false,
    audit_log_written: false,
    rollback_receipt_created: false,
    operator_dispatch_allowed: false,
    operator_live_dispatch_enabled: false,
    live_run_allowed: false,
    dispatch_allowed: false,
    dispatch_performed: false,
    budget_reservation_allowed: false,
    budget_reserved: false,
    provider_execution_allowed: false,
    provider_calls_made: false,
    retrieval_allowed: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutation_allowed: false,
    graph_mutated: false,
    final_artifact_allowed: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "repository transaction plan only: no transaction, queue claim, claim transaction, worker runtime, scheduler job, or runner dispatch is created",
    ],
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

    await user.click(screen.getByRole("button", { name: "Live settings" }));

    await waitFor(() => expect(liveRunActivationSettingsMidnightOil).toHaveBeenCalled());
    expect(liveRunActivationSettingsMidnightOil).toHaveBeenCalledWith({
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
      requested_live_run_enabled: true,
      requested_price_ceiling_usd: 12,
      requested_work_minutes: 90,
    });
    expect(screen.getByText("Settings receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-live-run-activation-settings")).toBeTruthy();
    expect(screen.getByText("blocked live run activation disabled")).toBeTruthy();
    expect(screen.getByText("live run activation controls missing")).toBeTruthy();
    expect(screen.getByText("6 controls")).toBeTruthy();
    expect(screen.getByText("blocked")).toBeTruthy();

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
      live_run_activation_settings_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-run-activation-settings",
      }),
      dispatch_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-dispatch-receipt",
      }),
    });
    expect(screen.getByText("Activation receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-activation-checklist")).toBeTruthy();
    expect(screen.getByText("activation blocked controls missing")).toBeTruthy();
    expect(screen.getByText("3 controls")).toBeTruthy();
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

    await user.click(screen.getByRole("button", { name: "Graph mutation" }));

    await waitFor(() => expect(graphMutationMidnightOil).toHaveBeenCalled());
    expect(graphMutationMidnightOil).toHaveBeenCalledWith({
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
      retrieval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval",
      }),
    });
    expect(screen.getByText("Graph receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-graph-mutation")).toBeTruthy();
    expect(screen.getByText("blocked graph mutation disabled")).toBeTruthy();
    expect(screen.getByText("graph mutation writer missing")).toBeTruthy();
    expect(screen.getByText("not mutated")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Final artifact" }));

    await waitFor(() => expect(finalArtifactMidnightOil).toHaveBeenCalled());
    expect(finalArtifactMidnightOil).toHaveBeenCalledWith({
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
      retrieval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval",
      }),
      graph_mutation_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-mutation",
      }),
    });
    expect(screen.getByText("Artifact receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact")).toBeTruthy();
    expect(screen.getByText("blocked final artifact writer disabled")).toBeTruthy();
    expect(screen.getByText("final html artifact writer missing")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-html-research-asset")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-twin-note-document")).toBeTruthy();
    expect(screen.getAllByText("not created").length).toBeGreaterThan(1);

    await user.click(screen.getByRole("button", { name: "Runner readiness" }));

    await waitFor(() => expect(runnerReadinessMidnightOil).toHaveBeenCalled());
    expect(runnerReadinessMidnightOil).toHaveBeenCalledWith({
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
      live_run_activation_settings_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-run-activation-settings",
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
      retrieval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval",
      }),
      graph_mutation_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-mutation",
      }),
      final_artifact_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact",
      }),
    });
    expect(screen.getByText("Readiness receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-readiness")).toBeTruthy();
    expect(screen.getByText("blocked runner readiness controls missing")).toBeTruthy();
    expect(screen.getByText("6")).toBeTruthy();
    expect(screen.getByText("operator live-run dispatch enablement")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Runner control plan" }));

    await waitFor(() => expect(runnerControlPlanMidnightOil).toHaveBeenCalled());
    expect(runnerControlPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_readiness_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-readiness",
      }),
    });
    expect(screen.getByText("Control plan receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-control-plan")).toBeTruthy();
    expect(screen.getByText("blocked runner controls unimplemented")).toBeTruthy();
    expect(screen.getAllByText("budget reservation provider").length).toBeGreaterThan(1);
    expect(screen.getByText("Budget reservation provider with idempotent no-overrun holds.")).toBeTruthy();
    expect(screen.getByText("Provider route executor that records route receipts before calls.")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Budget provider adapter" }));

    await waitFor(() => expect(budgetProviderAdapterPlanMidnightOil).toHaveBeenCalled());
    expect(budgetProviderAdapterPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
    });
    expect(screen.getByText("Adapter plan receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-budget-provider-adapter-plan")).toBeTruthy();
    expect(screen.getByText("blocked budget provider adapter unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-budget-provider-adapter")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-budget-reservation-ledger")).toBeTruthy();
    expect(screen.getByText("adapter must reject reservations above the approved price ceiling")).toBeTruthy();
    expect(screen.getByText(/Ledger fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Provider executor adapter" }));

    await waitFor(() => expect(providerExecutorAdapterPlanMidnightOil).toHaveBeenCalled());
    expect(providerExecutorAdapterPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
    });
    expect(screen.getByText("Provider executor adapter receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-provider-executor-adapter-plan")).toBeTruthy();
    expect(screen.getByText("blocked provider executor adapter unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-provider-executor-adapter")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-provider-route-ledger")).toBeTruthy();
    expect(
      screen.getByText("executor must require an active budget reservation before any provider call"),
    ).toBeTruthy();
    expect(screen.getByText(/Route receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Retrieval adapter" }));

    await waitFor(() => expect(retrievalAdapterPlanMidnightOil).toHaveBeenCalled());
    expect(retrievalAdapterPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
    });
    expect(screen.getByText("Retrieval adapter receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-retrieval-adapter-plan")).toBeTruthy();
    expect(screen.getByText("blocked retrieval adapter unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-retrieval-adapter")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-source-receipt-ledger")).toBeTruthy();
    expect(
      screen.getByText("retrieval adapter must require provider route receipts before source access"),
    ).toBeTruthy();
    expect(screen.getByText(/Source receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Graph adapter" }));

    await waitFor(() => expect(graphAdapterPlanMidnightOil).toHaveBeenCalled());
    expect(graphAdapterPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
    });
    expect(screen.getByText("Graph adapter receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-graph-adapter-plan")).toBeTruthy();
    expect(screen.getByText("blocked graph adapter unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-graph-adapter")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-graph-mutation-ledger")).toBeTruthy();
    expect(
      screen.getByText("graph adapter must require source receipts before any graph write"),
    ).toBeTruthy();
    expect(screen.getByText(/Graph receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Final artifact adapter" }));

    await waitFor(() => expect(finalArtifactAdapterPlanMidnightOil).toHaveBeenCalled());
    expect(finalArtifactAdapterPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
    });
    expect(screen.getByText("Final artifact adapter receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-adapter-plan")).toBeTruthy();
    expect(screen.getByText("blocked final artifact adapter unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-html-artifact-writer")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-artifact-receipt-ledger")).toBeTruthy();
    expect(screen.getAllByText("midnight-oil-test-html-research-asset").length).toBeGreaterThan(1);
    expect(screen.getAllByText("midnight-oil-test-twin-note-document").length).toBeGreaterThan(1);
    expect(
      screen.getByText(
        "final artifact adapter must require route, source, and graph receipts before writing HTML",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Artifact receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Operator dispatch adapter" }));

    await waitFor(() => expect(operatorDispatchAdapterPlanMidnightOil).toHaveBeenCalled());
    expect(operatorDispatchAdapterPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
    });
    expect(screen.getByText("Operator dispatch adapter receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-dispatch-adapter-plan")).toBeTruthy();
    expect(screen.getByText("blocked operator dispatch adapter unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-live-dispatch-setting")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-dispatch-control-ledger")).toBeTruthy();
    expect(screen.getByText("operator live dispatch enablement")).toBeTruthy();
    expect(
      screen.getByText(
        "operator dispatch adapter must require every implementation adapter plan before live enablement",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Dispatch enablement fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Control ledger adapter" }));

    await waitFor(() => expect(controlLedgerAdapterPlanMidnightOil).toHaveBeenCalled());
    expect(controlLedgerAdapterPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
    });
    expect(screen.getByText("Control ledger adapter receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-control-ledger-adapter-plan")).toBeTruthy();
    expect(screen.getByText("blocked control ledger adapter unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-dispatch-audit-log")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-dispatch-rollback-receipt")).toBeTruthy();
    expect(screen.getByText("operator dispatch control ledger")).toBeTruthy();
    expect(
      screen.getByText(
        "control ledger adapter must persist exactly one enablement row per approved run id and idempotency key",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Control ledger fields:/)).toBeTruthy();
    expect(screen.getByText(/Rollback receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Control ledger persistence" }));

    await waitFor(() => expect(controlLedgerPersistencePlanMidnightOil).toHaveBeenCalled());
    expect(controlLedgerPersistencePlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
    });
    expect(screen.getByText("Control ledger persistence receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-control-ledger-persistence-plan")).toBeTruthy();
    expect(screen.getByText("blocked control ledger persistence unimplemented")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-dispatch-control-repository"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-dispatch-control-transaction"),
    ).toBeTruthy();
    expect(screen.getByText("operator dispatch control ledger persistence")).toBeTruthy();
    expect(
      screen.getByText(
        "control ledger persistence must commit setting, ledger, audit log, and rollback receipt atomically",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Storage tables:/)).toBeTruthy();
    expect(screen.getByText(/Apply fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Control ledger persistence apply" }));

    await waitFor(() => expect(controlLedgerPersistenceApplyPlanMidnightOil).toHaveBeenCalled());
    expect(controlLedgerPersistenceApplyPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
    });
    expect(screen.getByText("Control ledger persistence apply receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-control-ledger-persistence-apply-plan")).toBeTruthy();
    expect(screen.getByText("blocked control ledger persistence apply unimplemented")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-dispatch-control-commit-receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-dispatch-control-persistence-content-digest",
      ),
    ).toBeTruthy();
    expect(screen.getByText("operator dispatch control ledger persistence apply")).toBeTruthy();
    expect(
      screen.getByText(
        "apply planner must require the persistence implementation plan before any transaction is opened",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Commit receipt fields:/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", { name: "Operator dispatch activation readiness" }),
    );

    await waitFor(() =>
      expect(operatorDispatchActivationReadinessPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(operatorDispatchActivationReadinessPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
      control_ledger_persistence_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
      }),
    });
    expect(screen.getByText("Operator dispatch activation readiness receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-dispatch-activation-readiness-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked operator dispatch activation readiness unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-dispatch-activation-readiness-receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-dispatch-live-enable-activation"),
    ).toBeTruthy();
    expect(screen.getByText("operator dispatch activation readiness")).toBeTruthy();
    expect(
      screen.getByText(
        "activation readiness must require a committed control ledger persistence receipt before live dispatch can be enabled",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Readiness blockers:/)).toBeTruthy();
    expect(screen.getByText(/Activation receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Live dispatch final enablement" }));

    await waitFor(() => expect(liveDispatchFinalEnablementPlanMidnightOil).toHaveBeenCalled());
    expect(liveDispatchFinalEnablementPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
      control_ledger_persistence_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
      }),
      operator_dispatch_activation_readiness_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-activation-readiness-plan",
      }),
    });
    expect(screen.getByText("Live dispatch final enablement receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-live-dispatch-final-enablement-plan")).toBeTruthy();
    expect(screen.getByText("blocked live dispatch final enablement unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-live-dispatch-final-enable-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-midnight-oil-runner-dispatch")).toBeTruthy();
    expect(screen.getByText("live dispatch final enablement")).toBeTruthy();
    expect(
      screen.getByText(
        "final enablement must require an activation readiness receipt that is activation_ready before live dispatch can be enabled",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Final blockers:/)).toBeTruthy();
    expect(screen.getByText(/Enablement receipt fields:/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", { name: "Live dispatch final enablement apply" }),
    );

    await waitFor(() =>
      expect(liveDispatchFinalEnablementApplyPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(liveDispatchFinalEnablementApplyPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
      control_ledger_persistence_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
      }),
      operator_dispatch_activation_readiness_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-activation-readiness-plan",
      }),
      live_dispatch_final_enablement_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-plan",
      }),
    });
    expect(screen.getByText("Live dispatch final enablement apply receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-live-dispatch-final-enablement-apply-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked live dispatch final enablement apply unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-live-dispatch-final-enable-apply-receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-live-dispatch-final-enable-idempotency-key"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-live-dispatch-final-enable-transaction"),
    ).toBeTruthy();
    expect(screen.getByText("live dispatch final enablement apply")).toBeTruthy();
    expect(
      screen.getByText(
        "apply planner must require an activation-ready receipt before any final enablement transaction is opened",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Apply blockers:/)).toBeTruthy();
    expect(screen.getByText(/Apply receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Runner dispatch scheduler" }));

    await waitFor(() => expect(runnerDispatchSchedulerPlanMidnightOil).toHaveBeenCalled());
    expect(runnerDispatchSchedulerPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
      control_ledger_persistence_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
      }),
      operator_dispatch_activation_readiness_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-activation-readiness-plan",
      }),
      live_dispatch_final_enablement_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-plan",
      }),
      live_dispatch_final_enablement_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
      }),
    });
    expect(screen.getByText("Runner dispatch scheduler receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-dispatch-scheduler-plan")).toBeTruthy();
    expect(screen.getByText("blocked runner dispatch scheduler unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-dispatch-scheduler-job")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-dispatch-queue")).toBeTruthy();
    expect(
      screen.getAllByText("midnight-oil-test-midnight-oil-runner-dispatch").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-live-dispatch-final-enable-idempotency-key")
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("runner dispatch scheduler").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "scheduler planner must require a final enablement apply receipt before any scheduler job is created",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Scheduler blockers:/)).toBeTruthy();
    expect(screen.getByText(/Scheduler receipt fields:/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", { name: "Runner dispatch worker bootstrap" }),
    );

    await waitFor(() =>
      expect(runnerDispatchWorkerBootstrapPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(runnerDispatchWorkerBootstrapPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
      control_ledger_persistence_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
      }),
      operator_dispatch_activation_readiness_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-activation-readiness-plan",
      }),
      live_dispatch_final_enablement_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-plan",
      }),
      live_dispatch_final_enablement_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
      }),
      runner_dispatch_scheduler_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-dispatch-scheduler-plan",
      }),
    });
    expect(screen.getByText("Runner dispatch worker bootstrap receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-runner-dispatch-worker-bootstrap-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked runner dispatch worker bootstrap unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-runner-dispatch-worker-bootstrap"),
    ).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-dispatch-worker")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-dispatch-worker-lease")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-runner-dispatch-retry-policy")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-runner-dispatch-dead-letter-queue"),
    ).toBeTruthy();
    expect(
      screen.getAllByText("midnight-oil-test-runner-dispatch-scheduler-job").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-runner-dispatch-queue").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("runner dispatch worker bootstrap").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "worker bootstrap planner must require a runner dispatch scheduler plan before any worker is created",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Worker blockers:/)).toBeTruthy();
    expect(screen.getByText(/Worker receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Scheduler lease retry plan" }));

    await waitFor(() => expect(schedulerLeaseRetryPlanMidnightOil).toHaveBeenCalled());
    expect(schedulerLeaseRetryPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
      control_ledger_persistence_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
      }),
      operator_dispatch_activation_readiness_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-activation-readiness-plan",
      }),
      live_dispatch_final_enablement_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-plan",
      }),
      live_dispatch_final_enablement_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
      }),
      runner_dispatch_scheduler_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-dispatch-scheduler-plan",
      }),
      runner_dispatch_worker_bootstrap_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
      }),
    });
    expect(screen.getByText("Scheduler lease retry receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-scheduler-lease-retry-plan")).toBeTruthy();
    expect(screen.getByText("blocked scheduler lease retry unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-scheduler-lease-policy")).toBeTruthy();
    expect(screen.getAllByText("midnight-oil-test-runner-dispatch-retry-policy").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-runner-dispatch-dead-letter-queue").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("900s")).toBeTruthy();
    expect(screen.getByText("exponential jitter")).toBeTruthy();
    expect(screen.getAllByText("scheduler lease retry").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "lease retry planner must require a worker bootstrap plan before any lease policy is created",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Lease retry blockers:/)).toBeTruthy();
    expect(screen.getByText(/Lease retry receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Worker queue claim plan" }));

    await waitFor(() => expect(workerQueueClaimPlanMidnightOil).toHaveBeenCalled());
    expect(workerQueueClaimPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
      control_ledger_persistence_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
      }),
      operator_dispatch_activation_readiness_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-activation-readiness-plan",
      }),
      live_dispatch_final_enablement_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-plan",
      }),
      live_dispatch_final_enablement_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
      }),
      runner_dispatch_scheduler_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-dispatch-scheduler-plan",
      }),
      runner_dispatch_worker_bootstrap_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
      }),
      scheduler_lease_retry_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
      }),
    });
    expect(screen.getByText("Worker queue claim receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-queue-claim-plan")).toBeTruthy();
    expect(screen.getByText("blocked worker queue claim unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-queue-claim")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-queue-claim-transaction")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-queue-claim-lease-token")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-queue-claim-cursor")).toBeTruthy();
    expect(screen.getAllByText("midnight-oil-test-runner-dispatch-queue").length).toBeGreaterThan(0);
    expect(screen.getAllByText("midnight-oil-test-runner-dispatch-worker-lease").length).toBeGreaterThan(0);
    expect(screen.getAllByText("900s").length).toBeGreaterThan(0);
    expect(screen.getAllByText("exponential jitter").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/worker queue claim/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "worker queue claim planner must require scheduler lease retry planning before any queue item can be claimed",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Queue claim blockers:/)).toBeTruthy();
    expect(screen.getByText(/Queue claim receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Repository transaction plan" }));

    await waitFor(() => expect(repositoryTransactionPlanMidnightOil).toHaveBeenCalled());
    expect(repositoryTransactionPlanMidnightOil).toHaveBeenCalledWith({
      launch_packet: expect.objectContaining({
        packet_id: "midnight-oil-test-launch-packet",
      }),
      approval_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-approval-receipt",
      }),
      runner_handoff: expect.objectContaining({
        handoff_id: "midnight-oil-test-runner-handoff",
      }),
      runner_control_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-control-plan",
      }),
      budget_provider_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-budget-provider-adapter-plan",
      }),
      provider_executor_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-provider-executor-adapter-plan",
      }),
      retrieval_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-retrieval-adapter-plan",
      }),
      graph_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-graph-adapter-plan",
      }),
      final_artifact_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-adapter-plan",
      }),
      operator_dispatch_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-adapter-plan",
      }),
      control_ledger_adapter_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-adapter-plan",
      }),
      control_ledger_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-plan",
      }),
      control_ledger_persistence_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-control-ledger-persistence-apply-plan",
      }),
      operator_dispatch_activation_readiness_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-operator-dispatch-activation-readiness-plan",
      }),
      live_dispatch_final_enablement_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-plan",
      }),
      live_dispatch_final_enablement_apply_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-live-dispatch-final-enablement-apply-plan",
      }),
      runner_dispatch_scheduler_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-dispatch-scheduler-plan",
      }),
      runner_dispatch_worker_bootstrap_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
      }),
      scheduler_lease_retry_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
      }),
      worker_queue_claim_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-queue-claim-plan",
      }),
    });
    expect(screen.getByText("Repository transaction receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-repository-transaction-plan")).toBeTruthy();
    expect(screen.getByText("blocked repository transaction unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-repository-transaction")).toBeTruthy();
    expect(screen.getByText("worker queue claim commit")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-repository-transaction-write-set")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-repository-transaction-lock")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-repository-transaction-commit-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-repository-transaction-rollback-receipt")).toBeTruthy();
    expect(screen.getAllByText("midnight-oil-test-worker-queue-claim").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "repository transaction planner must require worker queue-claim planning before any queue claim can be committed",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Repository transaction blockers:/)).toBeTruthy();
    expect(screen.getByText(/Repository transaction receipt fields:/)).toBeTruthy();
  });
});
