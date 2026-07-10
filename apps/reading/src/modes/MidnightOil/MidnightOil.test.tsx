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
  deliveryNotificationReconciliationPlanMidnightOil,
  dispatchMidnightOil,
  dryRunMidnightOil,
  finalArtifactAdapterPlanMidnightOil,
  finalArtifactCompletionFinalizationPlanMidnightOil,
  finalArtifactGraphCommitPlanMidnightOil,
  finalArtifactMidnightOil,
  finalArtifactPersistencePlanMidnightOil,
  finalArtifactPublishPlanMidnightOil,
  finalCloseoutArchiveReconciliationPlanMidnightOil,
  finalRunClosurePlanMidnightOil,
  finalHtmlArtifactAssemblyPlanMidnightOil,
  finalSynthesisDraftPlanMidnightOil,
  graphAdapterPlanMidnightOil,
  graphMutationMidnightOil,
  liveDispatchFinalEnablementApplyPlanMidnightOil,
  liveDispatchFinalEnablementPlanMidnightOil,
  liveRunActivationSettingsMidnightOil,
  operatorArchiveHandoffPackageDeliveryAuditPlanMidnightOil,
  operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanMidnightOil,
  operatorArchiveHandoffPackagePlanMidnightOil,
  operatorArchiveHandoffPackageResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportDeliveryConfirmationPlanMidnightOil,
  operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanMidnightOil,
  operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanMidnightOil,
  operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanMidnightOil,
  operatorArchivePackageDeliveryReportPlanMidnightOil,
  operatorArchivePackageDeliveryReportNotificationReadinessPlanMidnightOil,
  operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportResultReconciliationPlanMidnightOil,
  operatorDeliveryLedgerReconciliationPlanMidnightOil,
  operatorDispatchActivationReadinessPlanMidnightOil,
  operatorDispatchAdapterPlanMidnightOil,
  operatorNotificationDeliveryApplyPlanMidnightOil,
  operatorNotificationDeliveryReadinessPlanMidnightOil,
  operatorNotificationDeliveryResultReconciliationPlanMidnightOil,
  preflightMidnightOil,
  providerExecutorAdapterPlanMidnightOil,
  providerRouteMidnightOil,
  repositoryCommitRollbackPlanMidnightOil,
  repositoryTransactionPlanMidnightOil,
  retentionBillingReconciliationPlanMidnightOil,
  retrievalAdapterPlanMidnightOil,
  retrievalMidnightOil,
  runnerControlPlanMidnightOil,
  runnerDispatchSchedulerPlanMidnightOil,
  runnerDispatchWorkerBootstrapPlanMidnightOil,
  runnerReadinessMidnightOil,
  schedulerLeaseRetryPlanMidnightOil,
  synthesisBundleAssemblyPlanMidnightOil,
  workerCancellationAbandonPlanMidnightOil,
  workerCompletionFinalizationPlanMidnightOil,
  workerDispatchLeaseHeartbeatPlanMidnightOil,
  workerOutputAggregationPlanMidnightOil,
  workerQueueClaimPlanMidnightOil,
  workerSynthesisHandoffPlanMidnightOil,
  workspaceDeliveryCardReconciliationPlanMidnightOil,
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
  repositoryCommitRollbackPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
    repository_transaction_plan_receipt_id: "midnight-oil-test-repository-transaction-plan",
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
    status: "blocked_repository_commit_rollback_unimplemented",
    adapter_key: "repository_commit_rollback",
    planned_repository_transaction_id: "midnight-oil-test-repository-transaction",
    planned_transaction_scope: "worker_queue_claim_commit",
    planned_write_set_id: "midnight-oil-test-repository-transaction-write-set",
    planned_lock_id: "midnight-oil-test-repository-transaction-lock",
    planned_commit_receipt_id: "midnight-oil-test-repository-transaction-commit-receipt",
    planned_rollback_receipt_id: "midnight-oil-test-repository-transaction-rollback-receipt",
    planned_commit_ledger_entry_id: "midnight-oil-test-repository-commit-ledger-entry",
    planned_rollback_ledger_entry_id: "midnight-oil-test-repository-rollback-ledger-entry",
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
    repository_commit_rollback_blockers: [
      "commit receipt durable writer",
      "rollback receipt durable writer",
      "commit ledger append transaction",
      "rollback ledger append transaction",
      "idempotent commit/rollback replay protection",
    ],
    required_repository_commit_rollback_invariants: [
      "repository commit rollback planner must require repository transaction planning before any commit or rollback receipt can be created",
      "repository commit rollback planner must keep commit and rollback receipts paired to the same transaction id, write set id, lock id, and idempotency key",
    ],
    required_repository_commit_rollback_receipt_fields: [
      "repository_commit_rollback_plan_receipt_id",
      "repository_transaction_plan_receipt_id",
      "repository_transaction_id",
      "write_set_id",
      "lock_id",
      "commit_receipt_id",
      "rollback_receipt_id",
      "commit_ledger_entry_id",
      "rollback_ledger_entry_id",
      "queue_claim_id",
      "claim_transaction_id",
      "idempotency_key",
      "repository_transaction_committed",
    ],
    blocker_reason: "repository_commit_rollback_unimplemented",
    repository_commit_allowed: false,
    repository_rollback_allowed: false,
    commit_receipt_created: false,
    rollback_receipt_created: false,
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
      "repository commit rollback plan only: no transaction, queue claim, claim transaction, worker runtime, scheduler job, or runner dispatch is created",
    ],
  })),
  workerDispatchLeaseHeartbeatPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
    repository_commit_rollback_plan_receipt_id:
      "midnight-oil-test-repository-commit-rollback-plan",
    repository_transaction_plan_receipt_id: "midnight-oil-test-repository-transaction-plan",
    worker_queue_claim_plan_receipt_id: "midnight-oil-test-worker-queue-claim-plan",
    scheduler_lease_retry_plan_receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_worker_dispatch_lease_heartbeat_unimplemented",
    adapter_key: "worker_dispatch_lease_heartbeat",
    planned_heartbeat_receipt_id: "midnight-oil-test-worker-lease-heartbeat-receipt",
    planned_lease_renewal_receipt_id: "midnight-oil-test-worker-lease-renewal-receipt",
    planned_lease_expiry_receipt_id: "midnight-oil-test-worker-lease-expiry-receipt",
    planned_heartbeat_ledger_entry_id:
      "midnight-oil-test-worker-lease-heartbeat-ledger-entry",
    planned_queue_claim_id: "midnight-oil-test-worker-queue-claim",
    planned_claim_lease_token_id: "midnight-oil-test-worker-queue-claim-lease-token",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_visibility_timeout_seconds: 900,
    planned_lease_ttl_seconds: 300,
    planned_heartbeat_interval_seconds: 60,
    planned_max_missed_heartbeats: 3,
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    worker_dispatch_lease_heartbeat_blockers: [
      "worker lease heartbeat writer",
      "worker lease renewal compare-and-swap",
      "worker lease expiry monitor",
      "heartbeat ledger append transaction",
      "stale lease recovery policy",
    ],
    required_worker_dispatch_lease_heartbeat_invariants: [
      "worker dispatch lease heartbeat planner must require repository commit rollback planning before any worker heartbeat can be recorded",
      "worker dispatch lease heartbeat planner must keep heartbeat, renewal, and expiry receipts tied to the same queue claim lease token",
    ],
    required_worker_dispatch_lease_heartbeat_receipt_fields: [
      "worker_dispatch_lease_heartbeat_plan_receipt_id",
      "repository_commit_rollback_plan_receipt_id",
      "worker_lease_id",
      "heartbeat_receipt_id",
      "lease_renewal_receipt_id",
      "lease_expiry_receipt_id",
      "heartbeat_ledger_entry_id",
      "idempotency_key",
    ],
    blocker_reason: "worker_dispatch_lease_heartbeat_unimplemented",
    worker_lease_heartbeat_allowed: false,
    worker_lease_heartbeat_recorded: false,
    worker_lease_renewal_allowed: false,
    worker_lease_renewed: false,
    worker_lease_expiry_allowed: false,
    worker_lease_expired: false,
    worker_started: false,
    repository_commit_allowed: false,
    repository_rollback_allowed: false,
    commit_receipt_created: false,
    rollback_receipt_created: false,
    repository_transaction_allowed: false,
    repository_transaction_opened: false,
    repository_transaction_committed: false,
    queue_claim_allowed: false,
    queue_claim_created: false,
    claim_transaction_opened: false,
    claim_transaction_committed: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
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
      "worker dispatch lease heartbeat plan only: no heartbeat, renewal, expiry, repository commit, worker runtime, or runner dispatch is created",
    ],
  })),
  workerCancellationAbandonPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
    worker_dispatch_lease_heartbeat_plan_receipt_id:
      "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
    repository_commit_rollback_plan_receipt_id:
      "midnight-oil-test-repository-commit-rollback-plan",
    repository_transaction_plan_receipt_id: "midnight-oil-test-repository-transaction-plan",
    worker_queue_claim_plan_receipt_id: "midnight-oil-test-worker-queue-claim-plan",
    scheduler_lease_retry_plan_receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_worker_cancellation_abandon_unimplemented",
    adapter_key: "worker_cancellation_abandon",
    planned_cancellation_receipt_id: "midnight-oil-test-worker-cancellation-receipt",
    planned_abandon_receipt_id: "midnight-oil-test-worker-abandon-receipt",
    planned_cancellation_ledger_entry_id:
      "midnight-oil-test-worker-cancellation-ledger-entry",
    planned_abandon_ledger_entry_id: "midnight-oil-test-worker-abandon-ledger-entry",
    planned_queue_claim_id: "midnight-oil-test-worker-queue-claim",
    planned_claim_lease_token_id: "midnight-oil-test-worker-queue-claim-lease-token",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_visibility_timeout_seconds: 900,
    planned_lease_ttl_seconds: 300,
    planned_abandon_after_missed_heartbeats: 3,
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    worker_cancellation_abandon_blockers: [
      "worker cancellation signal writer",
      "worker abandon compare-and-swap",
      "worker lease release transaction",
      "cancellation ledger append transaction",
      "abandoned claim recovery policy",
    ],
    required_worker_cancellation_abandon_invariants: [
      "worker cancellation abandon planner must require worker dispatch lease heartbeat planning before any worker can be cancelled or abandoned",
      "worker cancellation abandon planner must keep cancellation and abandon receipts tied to the same queue claim lease token",
    ],
    required_worker_cancellation_abandon_receipt_fields: [
      "worker_cancellation_abandon_plan_receipt_id",
      "worker_dispatch_lease_heartbeat_plan_receipt_id",
      "cancellation_receipt_id",
      "abandon_receipt_id",
      "cancellation_ledger_entry_id",
      "abandon_ledger_entry_id",
      "worker_cancelled",
      "worker_abandoned",
      "idempotency_key",
    ],
    blocker_reason: "worker_cancellation_abandon_unimplemented",
    worker_cancellation_allowed: false,
    worker_cancelled: false,
    worker_abandon_allowed: false,
    worker_abandoned: false,
    worker_lease_heartbeat_allowed: false,
    worker_lease_heartbeat_recorded: false,
    worker_lease_renewal_allowed: false,
    worker_lease_renewed: false,
    worker_lease_expiry_allowed: false,
    worker_lease_expired: false,
    worker_started: false,
    repository_commit_allowed: false,
    repository_rollback_allowed: false,
    commit_receipt_created: false,
    rollback_receipt_created: false,
    repository_transaction_allowed: false,
    repository_transaction_opened: false,
    repository_transaction_committed: false,
    queue_claim_allowed: false,
    queue_claim_created: false,
    claim_transaction_opened: false,
    claim_transaction_committed: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
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
      "worker cancellation abandon plan only: no worker cancellation, worker abandon, lease release, worker runtime, scheduler job, or runner dispatch is created",
    ],
  })),
  workerCompletionFinalizationPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-worker-completion-finalization-plan",
    worker_cancellation_abandon_plan_receipt_id:
      "midnight-oil-test-worker-cancellation-abandon-plan",
    worker_dispatch_lease_heartbeat_plan_receipt_id:
      "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
    repository_commit_rollback_plan_receipt_id:
      "midnight-oil-test-repository-commit-rollback-plan",
    repository_transaction_plan_receipt_id: "midnight-oil-test-repository-transaction-plan",
    worker_queue_claim_plan_receipt_id: "midnight-oil-test-worker-queue-claim-plan",
    scheduler_lease_retry_plan_receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_worker_completion_finalization_unimplemented",
    adapter_key: "worker_completion_finalization",
    planned_completion_receipt_id: "midnight-oil-test-worker-completion-receipt",
    planned_finalization_receipt_id: "midnight-oil-test-worker-finalization-receipt",
    planned_worker_result_manifest_id: "midnight-oil-test-worker-result-manifest",
    planned_worker_output_bundle_id: "midnight-oil-test-worker-output-bundle",
    planned_completion_ledger_entry_id:
      "midnight-oil-test-worker-completion-ledger-entry",
    planned_finalization_ledger_entry_id:
      "midnight-oil-test-worker-finalization-ledger-entry",
    planned_queue_claim_id: "midnight-oil-test-worker-queue-claim",
    planned_claim_lease_token_id: "midnight-oil-test-worker-queue-claim-lease-token",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    worker_completion_finalization_blockers: [
      "worker completion receipt writer",
      "worker result manifest durable writer",
      "worker output bundle durable writer",
      "worker finalization ledger append transaction",
      "idempotent worker completion replay protection",
    ],
    required_worker_completion_finalization_invariants: [
      "worker completion finalization planner must require worker cancellation abandon planning before any worker completion can be finalized",
      "worker completion finalization planner must preserve queue claim lease token lineage through completion and finalization",
    ],
    required_worker_completion_finalization_receipt_fields: [
      "worker_completion_finalization_plan_receipt_id",
      "worker_cancellation_abandon_plan_receipt_id",
      "worker_result_manifest_id",
      "worker_output_bundle_id",
      "worker_completed",
      "worker_finalized",
      "idempotency_key",
    ],
    blocker_reason: "worker_completion_finalization_unimplemented",
    worker_completion_allowed: false,
    worker_completed: false,
    worker_finalization_allowed: false,
    worker_finalized: false,
    worker_result_manifest_created: false,
    worker_output_bundle_created: false,
    worker_cancellation_allowed: false,
    worker_cancelled: false,
    worker_abandon_allowed: false,
    worker_abandoned: false,
    worker_lease_heartbeat_allowed: false,
    worker_lease_heartbeat_recorded: false,
    worker_lease_renewal_allowed: false,
    worker_lease_renewed: false,
    worker_lease_expiry_allowed: false,
    worker_lease_expired: false,
    worker_started: false,
    repository_commit_allowed: false,
    repository_rollback_allowed: false,
    commit_receipt_created: false,
    rollback_receipt_created: false,
    repository_transaction_allowed: false,
    repository_transaction_opened: false,
    repository_transaction_committed: false,
    queue_claim_allowed: false,
    queue_claim_created: false,
    claim_transaction_opened: false,
    claim_transaction_committed: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
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
      "worker completion finalization plan only: no completion, finalization, result manifest, output bundle, ledger write, or runner dispatch is created",
    ],
  })),
  workerOutputAggregationPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-worker-output-aggregation-plan",
    worker_completion_finalization_plan_receipt_id:
      "midnight-oil-test-worker-completion-finalization-plan",
    worker_cancellation_abandon_plan_receipt_id:
      "midnight-oil-test-worker-cancellation-abandon-plan",
    worker_dispatch_lease_heartbeat_plan_receipt_id:
      "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
    repository_commit_rollback_plan_receipt_id:
      "midnight-oil-test-repository-commit-rollback-plan",
    repository_transaction_plan_receipt_id: "midnight-oil-test-repository-transaction-plan",
    worker_queue_claim_plan_receipt_id: "midnight-oil-test-worker-queue-claim-plan",
    scheduler_lease_retry_plan_receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_worker_output_aggregation_unimplemented",
    adapter_key: "worker_output_aggregation",
    planned_worker_output_aggregation_receipt_id:
      "midnight-oil-test-worker-output-aggregation-receipt",
    planned_worker_output_index_id: "midnight-oil-test-worker-output-index",
    planned_worker_output_manifest_id: "midnight-oil-test-worker-output-manifest",
    planned_worker_output_summary_id: "midnight-oil-test-worker-output-summary",
    planned_worker_result_manifest_id: "midnight-oil-test-worker-result-manifest",
    planned_worker_output_bundle_id: "midnight-oil-test-worker-output-bundle",
    planned_output_aggregation_ledger_entry_id:
      "midnight-oil-test-worker-output-aggregation-ledger-entry",
    planned_queue_claim_id: "midnight-oil-test-worker-queue-claim",
    planned_claim_lease_token_id: "midnight-oil-test-worker-queue-claim-lease-token",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    worker_output_aggregation_blockers: [
      "worker output aggregation receipt writer",
      "worker output index durable writer",
      "worker output manifest normalization policy",
      "worker output summary synthesis boundary",
      "idempotent worker output aggregation replay protection",
    ],
    required_worker_output_aggregation_invariants: [
      "worker output aggregation planner must require worker completion finalization planning before any worker output can be aggregated",
      "worker output aggregation planner must preserve queue claim lease token lineage through aggregation",
    ],
    required_worker_output_aggregation_receipt_fields: [
      "worker_output_aggregation_plan_receipt_id",
      "worker_completion_finalization_plan_receipt_id",
      "worker_output_index_id",
      "worker_output_manifest_id",
      "worker_output_summary_id",
      "worker_output_aggregated",
      "idempotency_key",
    ],
    blocker_reason: "worker_output_aggregation_unimplemented",
    worker_output_aggregation_allowed: false,
    worker_output_aggregated: false,
    worker_output_index_created: false,
    worker_output_manifest_created: false,
    worker_output_summary_created: false,
    worker_completion_allowed: false,
    worker_completed: false,
    worker_finalization_allowed: false,
    worker_finalized: false,
    worker_result_manifest_created: false,
    worker_output_bundle_created: false,
    worker_cancellation_allowed: false,
    worker_cancelled: false,
    worker_abandon_allowed: false,
    worker_abandoned: false,
    worker_lease_heartbeat_allowed: false,
    worker_lease_heartbeat_recorded: false,
    worker_lease_renewal_allowed: false,
    worker_lease_renewed: false,
    worker_lease_expiry_allowed: false,
    worker_lease_expired: false,
    worker_started: false,
    repository_commit_allowed: false,
    repository_rollback_allowed: false,
    commit_receipt_created: false,
    rollback_receipt_created: false,
    repository_transaction_allowed: false,
    repository_transaction_opened: false,
    repository_transaction_committed: false,
    queue_claim_allowed: false,
    queue_claim_created: false,
    claim_transaction_opened: false,
    claim_transaction_committed: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
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
      "worker output aggregation plan only: no output aggregation, output index, output manifest, output summary, ledger write, or runner dispatch is created",
    ],
  })),
  workerSynthesisHandoffPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    worker_completion_finalization_plan_receipt_id:
      "midnight-oil-test-worker-completion-finalization-plan",
    worker_cancellation_abandon_plan_receipt_id:
      "midnight-oil-test-worker-cancellation-abandon-plan",
    worker_dispatch_lease_heartbeat_plan_receipt_id:
      "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
    repository_commit_rollback_plan_receipt_id:
      "midnight-oil-test-repository-commit-rollback-plan",
    repository_transaction_plan_receipt_id: "midnight-oil-test-repository-transaction-plan",
    worker_queue_claim_plan_receipt_id: "midnight-oil-test-worker-queue-claim-plan",
    scheduler_lease_retry_plan_receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_worker_synthesis_handoff_unimplemented",
    adapter_key: "worker_synthesis_handoff",
    planned_synthesis_handoff_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-receipt",
    planned_synthesis_input_bundle_id: "midnight-oil-test-worker-synthesis-input-bundle",
    planned_synthesis_context_manifest_id:
      "midnight-oil-test-worker-synthesis-context-manifest",
    planned_synthesis_outline_id: "midnight-oil-test-worker-synthesis-outline",
    planned_synthesis_handoff_ledger_entry_id:
      "midnight-oil-test-worker-synthesis-handoff-ledger-entry",
    planned_worker_output_aggregation_receipt_id:
      "midnight-oil-test-worker-output-aggregation-receipt",
    planned_worker_output_index_id: "midnight-oil-test-worker-output-index",
    planned_worker_output_manifest_id: "midnight-oil-test-worker-output-manifest",
    planned_worker_output_summary_id: "midnight-oil-test-worker-output-summary",
    planned_worker_result_manifest_id: "midnight-oil-test-worker-result-manifest",
    planned_worker_output_bundle_id: "midnight-oil-test-worker-output-bundle",
    planned_queue_claim_id: "midnight-oil-test-worker-queue-claim",
    planned_claim_lease_token_id: "midnight-oil-test-worker-queue-claim-lease-token",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    worker_synthesis_handoff_blockers: [
      "worker synthesis handoff receipt writer",
      "worker synthesis input bundle durable writer",
      "worker synthesis context manifest builder",
      "worker synthesis outline planner",
      "idempotent worker synthesis handoff replay protection",
    ],
    required_worker_synthesis_handoff_invariants: [
      "worker synthesis handoff planner must require worker output aggregation planning before synthesis input can be handed off",
      "worker synthesis handoff planner must preserve output aggregation receipt lineage through synthesis planning",
    ],
    required_worker_synthesis_handoff_receipt_fields: [
      "worker_synthesis_handoff_plan_receipt_id",
      "worker_output_aggregation_plan_receipt_id",
      "synthesis_input_bundle_id",
      "synthesis_context_manifest_id",
      "synthesis_outline_id",
      "worker_synthesis_handoff_created",
      "idempotency_key",
    ],
    blocker_reason: "worker_synthesis_handoff_unimplemented",
    worker_synthesis_handoff_allowed: false,
    worker_synthesis_handoff_created: false,
    synthesis_input_bundle_created: false,
    synthesis_context_manifest_created: false,
    synthesis_outline_created: false,
    worker_output_aggregation_allowed: false,
    worker_output_aggregated: false,
    worker_output_index_created: false,
    worker_output_manifest_created: false,
    worker_output_summary_created: false,
    worker_completion_allowed: false,
    worker_completed: false,
    worker_finalization_allowed: false,
    worker_finalized: false,
    worker_result_manifest_created: false,
    worker_output_bundle_created: false,
    worker_cancellation_allowed: false,
    worker_cancelled: false,
    worker_abandon_allowed: false,
    worker_abandoned: false,
    worker_lease_heartbeat_allowed: false,
    worker_lease_heartbeat_recorded: false,
    worker_lease_renewal_allowed: false,
    worker_lease_renewed: false,
    worker_lease_expiry_allowed: false,
    worker_lease_expired: false,
    worker_started: false,
    repository_commit_allowed: false,
    repository_rollback_allowed: false,
    commit_receipt_created: false,
    rollback_receipt_created: false,
    repository_transaction_allowed: false,
    repository_transaction_opened: false,
    repository_transaction_committed: false,
    queue_claim_allowed: false,
    queue_claim_created: false,
    claim_transaction_opened: false,
    claim_transaction_committed: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
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
      "worker synthesis handoff plan only: no synthesis handoff, input bundle, context manifest, outline, ledger write, or runner dispatch is created",
    ],
  })),
  synthesisBundleAssemblyPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-synthesis-bundle-assembly-plan",
    worker_synthesis_handoff_plan_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    worker_completion_finalization_plan_receipt_id:
      "midnight-oil-test-worker-completion-finalization-plan",
    worker_cancellation_abandon_plan_receipt_id:
      "midnight-oil-test-worker-cancellation-abandon-plan",
    worker_dispatch_lease_heartbeat_plan_receipt_id:
      "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
    repository_commit_rollback_plan_receipt_id:
      "midnight-oil-test-repository-commit-rollback-plan",
    repository_transaction_plan_receipt_id: "midnight-oil-test-repository-transaction-plan",
    worker_queue_claim_plan_receipt_id: "midnight-oil-test-worker-queue-claim-plan",
    scheduler_lease_retry_plan_receipt_id: "midnight-oil-test-scheduler-lease-retry-plan",
    runner_dispatch_worker_bootstrap_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-worker-bootstrap-plan",
    runner_dispatch_scheduler_plan_receipt_id:
      "midnight-oil-test-runner-dispatch-scheduler-plan",
    runner_control_plan_receipt_id: "midnight-oil-test-runner-control-plan",
    runner_readiness_receipt_id: "midnight-oil-test-runner-readiness",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    launch_packet_id: "midnight-oil-test-launch-packet",
    run_id: "midnight-oil-test",
    status: "blocked_synthesis_bundle_assembly_unimplemented",
    adapter_key: "synthesis_bundle_assembly",
    planned_synthesis_bundle_assembly_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-receipt",
    planned_synthesis_bundle_id: "midnight-oil-test-synthesis-bundle",
    planned_synthesis_source_packet_id: "midnight-oil-test-synthesis-source-packet",
    planned_synthesis_evidence_map_id: "midnight-oil-test-synthesis-evidence-map",
    planned_synthesis_composition_plan_id: "midnight-oil-test-synthesis-composition-plan",
    planned_synthesis_quality_gate_id: "midnight-oil-test-synthesis-quality-gate",
    planned_synthesis_handoff_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-receipt",
    planned_synthesis_input_bundle_id: "midnight-oil-test-worker-synthesis-input-bundle",
    planned_synthesis_context_manifest_id:
      "midnight-oil-test-worker-synthesis-context-manifest",
    planned_synthesis_outline_id: "midnight-oil-test-worker-synthesis-outline",
    planned_synthesis_handoff_ledger_entry_id:
      "midnight-oil-test-worker-synthesis-handoff-ledger-entry",
    planned_worker_output_aggregation_receipt_id:
      "midnight-oil-test-worker-output-aggregation-receipt",
    planned_worker_output_index_id: "midnight-oil-test-worker-output-index",
    planned_worker_output_manifest_id: "midnight-oil-test-worker-output-manifest",
    planned_worker_output_summary_id: "midnight-oil-test-worker-output-summary",
    planned_worker_result_manifest_id: "midnight-oil-test-worker-result-manifest",
    planned_worker_output_bundle_id: "midnight-oil-test-worker-output-bundle",
    planned_queue_claim_id: "midnight-oil-test-worker-queue-claim",
    planned_claim_lease_token_id: "midnight-oil-test-worker-queue-claim-lease-token",
    planned_queue_id: "midnight-oil-test-runner-dispatch-queue",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    synthesis_bundle_assembly_blockers: [
      "synthesis bundle assembly receipt writer",
      "synthesis source packet durable writer",
      "synthesis evidence map builder",
      "synthesis composition plan builder",
      "synthesis quality gate policy",
      "idempotent synthesis bundle assembly replay protection",
    ],
    required_synthesis_bundle_assembly_invariants: [
      "synthesis bundle assembly planner must require worker synthesis handoff planning before synthesis bundles can be assembled",
      "synthesis bundle assembly planner must preserve synthesis handoff lineage through bundle assembly",
    ],
    required_synthesis_bundle_assembly_receipt_fields: [
      "synthesis_bundle_assembly_plan_receipt_id",
      "worker_synthesis_handoff_plan_receipt_id",
      "synthesis_bundle_id",
      "synthesis_source_packet_id",
      "synthesis_evidence_map_id",
      "synthesis_composition_plan_id",
      "synthesis_quality_gate_id",
      "synthesis_bundle_assembled",
      "idempotency_key",
    ],
    blocker_reason: "synthesis_bundle_assembly_unimplemented",
    synthesis_bundle_assembly_allowed: false,
    synthesis_bundle_assembled: false,
    synthesis_source_packet_created: false,
    synthesis_evidence_map_created: false,
    synthesis_composition_plan_created: false,
    synthesis_quality_gate_created: false,
    worker_synthesis_handoff_allowed: false,
    worker_synthesis_handoff_created: false,
    synthesis_input_bundle_created: false,
    synthesis_context_manifest_created: false,
    synthesis_outline_created: false,
    worker_output_aggregation_allowed: false,
    worker_output_aggregated: false,
    worker_output_index_created: false,
    worker_output_manifest_created: false,
    worker_output_summary_created: false,
    worker_completion_allowed: false,
    worker_completed: false,
    worker_finalization_allowed: false,
    worker_finalized: false,
    worker_result_manifest_created: false,
    worker_output_bundle_created: false,
    worker_cancellation_allowed: false,
    worker_cancelled: false,
    worker_abandon_allowed: false,
    worker_abandoned: false,
    worker_lease_heartbeat_allowed: false,
    worker_lease_heartbeat_recorded: false,
    worker_lease_renewal_allowed: false,
    worker_lease_renewed: false,
    worker_lease_expiry_allowed: false,
    worker_lease_expired: false,
    worker_started: false,
    repository_commit_allowed: false,
    repository_rollback_allowed: false,
    commit_receipt_created: false,
    rollback_receipt_created: false,
    repository_transaction_allowed: false,
    repository_transaction_opened: false,
    repository_transaction_committed: false,
    queue_claim_allowed: false,
    queue_claim_created: false,
    claim_transaction_opened: false,
    claim_transaction_committed: false,
    scheduler_allowed: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
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
      "synthesis bundle assembly plan only: no synthesis bundle, source packet, evidence map, composition plan, quality gate, ledger write, or runner dispatch is created",
    ],
  })),
  finalSynthesisDraftPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-synthesis-draft-plan",
    synthesis_bundle_assembly_plan_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-plan",
    worker_synthesis_handoff_plan_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_final_synthesis_draft_unimplemented",
    adapter_key: "final_synthesis_draft",
    planned_final_synthesis_draft_receipt_id:
      "midnight-oil-test-final-synthesis-draft-receipt",
    planned_final_synthesis_draft_id: "midnight-oil-test-final-synthesis-draft",
    planned_final_synthesis_outline_id: "midnight-oil-test-final-synthesis-outline",
    planned_final_synthesis_claim_map_id: "midnight-oil-test-final-synthesis-claim-map",
    planned_final_synthesis_citation_map_id:
      "midnight-oil-test-final-synthesis-citation-map",
    planned_final_synthesis_gap_list_id: "midnight-oil-test-final-synthesis-gap-list",
    planned_final_synthesis_quality_report_id:
      "midnight-oil-test-final-synthesis-quality-report",
    planned_synthesis_bundle_assembly_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-receipt",
    planned_synthesis_bundle_id: "midnight-oil-test-synthesis-bundle",
    planned_synthesis_source_packet_id: "midnight-oil-test-synthesis-source-packet",
    planned_synthesis_evidence_map_id: "midnight-oil-test-synthesis-evidence-map",
    planned_synthesis_composition_plan_id: "midnight-oil-test-synthesis-composition-plan",
    planned_synthesis_quality_gate_id: "midnight-oil-test-synthesis-quality-gate",
    planned_synthesis_input_bundle_id: "midnight-oil-test-worker-synthesis-input-bundle",
    planned_synthesis_context_manifest_id:
      "midnight-oil-test-worker-synthesis-context-manifest",
    planned_synthesis_outline_id: "midnight-oil-test-worker-synthesis-outline",
    planned_worker_output_index_id: "midnight-oil-test-worker-output-index",
    planned_worker_output_manifest_id: "midnight-oil-test-worker-output-manifest",
    planned_worker_output_summary_id: "midnight-oil-test-worker-output-summary",
    planned_worker_result_manifest_id: "midnight-oil-test-worker-result-manifest",
    planned_worker_output_bundle_id: "midnight-oil-test-worker-output-bundle",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    final_synthesis_draft_blockers: [
      "final synthesis draft receipt writer",
      "final synthesis outline builder",
      "final synthesis claim map builder",
      "final synthesis citation map builder",
      "final synthesis gap list builder",
      "final synthesis quality report policy",
      "idempotent final synthesis draft replay protection",
    ],
    required_final_synthesis_draft_invariants: [
      "final synthesis draft planner must require synthesis bundle assembly planning before any final draft can be created",
      "final synthesis draft planner must preserve source/evidence/citation lineage through final draft planning",
    ],
    required_final_synthesis_draft_receipt_fields: [
      "final_synthesis_draft_plan_receipt_id",
      "synthesis_bundle_assembly_plan_receipt_id",
      "final_synthesis_draft_id",
      "final_synthesis_claim_map_id",
      "final_synthesis_citation_map_id",
      "final_synthesis_quality_report_id",
      "final_synthesis_draft_created",
      "idempotency_key",
    ],
    blocker_reason: "final_synthesis_draft_unimplemented",
    final_synthesis_draft_allowed: false,
    final_synthesis_draft_created: false,
    final_synthesis_outline_created: false,
    final_synthesis_claim_map_created: false,
    final_synthesis_citation_map_created: false,
    final_synthesis_gap_list_created: false,
    final_synthesis_quality_report_created: false,
    synthesis_bundle_assembly_allowed: false,
    synthesis_bundle_assembled: false,
    synthesis_source_packet_created: false,
    synthesis_evidence_map_created: false,
    synthesis_composition_plan_created: false,
    synthesis_quality_gate_created: false,
    worker_synthesis_handoff_created: false,
    synthesis_input_bundle_created: false,
    synthesis_context_manifest_created: false,
    synthesis_outline_created: false,
    worker_output_aggregated: false,
    worker_started: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "final synthesis draft plan only: no final draft, outline, claim map, citation map, gap list, quality report, ledger write, or runner dispatch is created",
    ],
  })),
  finalHtmlArtifactAssemblyPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-html-artifact-assembly-plan",
    final_synthesis_draft_plan_receipt_id:
      "midnight-oil-test-final-synthesis-draft-plan",
    synthesis_bundle_assembly_plan_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-plan",
    worker_synthesis_handoff_plan_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_final_html_artifact_assembly_unimplemented",
    adapter_key: "final_html_artifact_assembly",
    planned_final_html_artifact_assembly_receipt_id:
      "midnight-oil-test-final-html-artifact-assembly-receipt",
    planned_final_html_artifact_id: "midnight-oil-test-final-html-artifact",
    planned_final_html_asset_id: "midnight-oil-test-final-html-asset",
    planned_final_html_document_id: "midnight-oil-test-final-html-document",
    planned_final_html_twin_notes_document_id:
      "midnight-oil-test-final-html-twin-notes-document",
    planned_final_html_citation_index_id:
      "midnight-oil-test-final-html-citation-index",
    planned_final_html_export_manifest_id:
      "midnight-oil-test-final-html-export-manifest",
    planned_final_synthesis_draft_receipt_id:
      "midnight-oil-test-final-synthesis-draft-receipt",
    planned_final_synthesis_draft_id: "midnight-oil-test-final-synthesis-draft",
    planned_final_synthesis_outline_id: "midnight-oil-test-final-synthesis-outline",
    planned_final_synthesis_claim_map_id: "midnight-oil-test-final-synthesis-claim-map",
    planned_final_synthesis_citation_map_id:
      "midnight-oil-test-final-synthesis-citation-map",
    planned_final_synthesis_gap_list_id: "midnight-oil-test-final-synthesis-gap-list",
    planned_final_synthesis_quality_report_id:
      "midnight-oil-test-final-synthesis-quality-report",
    planned_synthesis_bundle_id: "midnight-oil-test-synthesis-bundle",
    planned_synthesis_source_packet_id: "midnight-oil-test-synthesis-source-packet",
    planned_synthesis_evidence_map_id: "midnight-oil-test-synthesis-evidence-map",
    planned_synthesis_composition_plan_id: "midnight-oil-test-synthesis-composition-plan",
    planned_synthesis_quality_gate_id: "midnight-oil-test-synthesis-quality-gate",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_worker_lease_id: "midnight-oil-test-runner-dispatch-worker-lease",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    final_html_artifact_assembly_blockers: [
      "final HTML artifact assembly receipt writer",
      "final HTML information asset writer",
      "final HTML document renderer",
      "twin note document linker",
      "citation index renderer",
      "HTML export manifest writer",
      "idempotent final HTML artifact assembly replay protection",
    ],
    required_final_html_artifact_assembly_invariants: [
      "final HTML artifact assembly planner must require final synthesis draft planning before any human-viewable HTML asset can be created",
      "final HTML artifact assembly planner must preserve source/evidence/citation lineage into every human-viewable HTML artifact",
    ],
    required_final_html_artifact_assembly_receipt_fields: [
      "final_html_artifact_assembly_plan_receipt_id",
      "final_synthesis_draft_plan_receipt_id",
      "final_html_artifact_id",
      "final_html_document_id",
      "final_html_twin_notes_document_id",
      "final_html_citation_index_id",
      "final_html_export_manifest_id",
      "final_html_artifact_assembled",
      "idempotency_key",
    ],
    blocker_reason: "final_html_artifact_assembly_unimplemented",
    final_html_artifact_assembly_allowed: false,
    final_html_artifact_assembled: false,
    final_html_asset_created: false,
    final_html_document_created: false,
    final_html_twin_notes_document_created: false,
    final_html_citation_index_created: false,
    final_html_export_manifest_created: false,
    final_synthesis_draft_created: false,
    final_synthesis_outline_created: false,
    final_synthesis_claim_map_created: false,
    final_synthesis_citation_map_created: false,
    final_synthesis_gap_list_created: false,
    final_synthesis_quality_report_created: false,
    synthesis_bundle_assembled: false,
    worker_output_aggregated: false,
    worker_started: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "final HTML artifact assembly plan only: no HTML asset, document, twin notes document, citation index, export manifest, graph mutation, or final artifact is created",
    ],
  })),
  finalArtifactPersistencePlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-artifact-persistence-plan",
    final_html_artifact_assembly_plan_receipt_id:
      "midnight-oil-test-final-html-artifact-assembly-plan",
    final_synthesis_draft_plan_receipt_id:
      "midnight-oil-test-final-synthesis-draft-plan",
    synthesis_bundle_assembly_plan_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-plan",
    worker_synthesis_handoff_plan_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_final_artifact_persistence_unimplemented",
    adapter_key: "final_artifact_persistence",
    planned_final_artifact_persistence_receipt_id:
      "midnight-oil-test-final-artifact-persistence-receipt",
    planned_persisted_final_artifact_id: "midnight-oil-test-persisted-final-artifact",
    planned_information_asset_id: "midnight-oil-test-information-asset",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_account_asset_binding_id: "midnight-oil-test-account-asset-binding",
    planned_twin_notes_binding_id: "midnight-oil-test-twin-notes-binding",
    planned_citation_index_binding_id: "midnight-oil-test-citation-index-binding",
    planned_graph_node_id: "midnight-oil-test-final-artifact-graph-node",
    planned_graph_edge_set_id: "midnight-oil-test-final-artifact-graph-edge-set",
    planned_artifact_ledger_entry_id: "midnight-oil-test-final-artifact-ledger-entry",
    planned_final_html_artifact_id: "midnight-oil-test-final-html-artifact",
    planned_final_html_asset_id: "midnight-oil-test-final-html-asset",
    planned_final_html_document_id: "midnight-oil-test-final-html-document",
    planned_final_html_twin_notes_document_id:
      "midnight-oil-test-final-html-twin-notes-document",
    planned_final_html_citation_index_id:
      "midnight-oil-test-final-html-citation-index",
    planned_final_html_export_manifest_id:
      "midnight-oil-test-final-html-export-manifest",
    planned_final_synthesis_draft_id: "midnight-oil-test-final-synthesis-draft",
    planned_synthesis_bundle_id: "midnight-oil-test-synthesis-bundle",
    planned_synthesis_source_packet_id: "midnight-oil-test-synthesis-source-packet",
    planned_synthesis_evidence_map_id: "midnight-oil-test-synthesis-evidence-map",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    final_artifact_persistence_blockers: [
      "final artifact persistence receipt writer",
      "information asset durable writer",
      "hosted HTML asset storage adapter",
      "account asset binding writer",
      "twin notes binding writer",
      "citation index binding writer",
      "artifact graph node writer",
      "artifact graph edge set writer",
      "artifact ledger entry writer",
      "idempotent final artifact persistence replay protection",
    ],
    required_final_artifact_persistence_invariants: [
      "final artifact persistence planner must require final HTML artifact assembly planning before any hosted information asset can be persisted",
      "final artifact persistence planner must preserve source/evidence/citation lineage through hosted HTML asset, graph node, and twin notes bindings",
    ],
    required_final_artifact_persistence_receipt_fields: [
      "final_artifact_persistence_plan_receipt_id",
      "final_html_artifact_assembly_plan_receipt_id",
      "persisted_final_artifact_id",
      "information_asset_id",
      "hosted_html_asset_id",
      "account_asset_binding_id",
      "twin_notes_binding_id",
      "citation_index_binding_id",
      "graph_node_id",
      "graph_edge_set_id",
      "artifact_ledger_entry_id",
      "final_artifact_persisted",
      "idempotency_key",
    ],
    blocker_reason: "final_artifact_persistence_unimplemented",
    final_artifact_persistence_allowed: false,
    final_artifact_persisted: false,
    information_asset_created: false,
    hosted_html_asset_created: false,
    account_asset_binding_created: false,
    twin_notes_binding_created: false,
    citation_index_binding_created: false,
    artifact_ledger_entry_created: false,
    graph_node_created: false,
    graph_edge_set_created: false,
    final_html_artifact_assembled: false,
    final_html_document_created: false,
    final_html_twin_notes_document_created: false,
    final_html_citation_index_created: false,
    final_synthesis_draft_created: false,
    synthesis_bundle_assembled: false,
    worker_output_aggregated: false,
    worker_started: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "final artifact persistence plan only: no hosted HTML asset, information asset, account binding, graph node, ledger entry, or final artifact is created",
    ],
  })),
  finalArtifactGraphCommitPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-artifact-graph-commit-plan",
    final_artifact_persistence_plan_receipt_id:
      "midnight-oil-test-final-artifact-persistence-plan",
    final_html_artifact_assembly_plan_receipt_id:
      "midnight-oil-test-final-html-artifact-assembly-plan",
    final_synthesis_draft_plan_receipt_id:
      "midnight-oil-test-final-synthesis-draft-plan",
    synthesis_bundle_assembly_plan_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-plan",
    worker_synthesis_handoff_plan_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_final_artifact_graph_commit_unimplemented",
    adapter_key: "final_artifact_graph_commit",
    planned_final_artifact_graph_commit_receipt_id:
      "midnight-oil-test-final-artifact-graph-commit-receipt",
    planned_graph_commit_id: "midnight-oil-test-final-artifact-graph-commit",
    planned_graph_transaction_id:
      "midnight-oil-test-final-artifact-graph-transaction",
    planned_graph_node_id: "midnight-oil-test-final-artifact-graph-node",
    planned_graph_edge_set_id: "midnight-oil-test-final-artifact-graph-edge-set",
    planned_graph_snapshot_id: "midnight-oil-test-final-artifact-graph-snapshot",
    planned_graph_lineage_index_id:
      "midnight-oil-test-final-artifact-graph-lineage-index",
    planned_information_asset_id: "midnight-oil-test-information-asset",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_artifact_ledger_entry_id: "midnight-oil-test-final-artifact-ledger-entry",
    planned_final_html_artifact_id: "midnight-oil-test-final-html-artifact",
    planned_final_html_document_id: "midnight-oil-test-final-html-document",
    planned_final_synthesis_draft_id: "midnight-oil-test-final-synthesis-draft",
    planned_synthesis_bundle_id: "midnight-oil-test-synthesis-bundle",
    planned_synthesis_source_packet_id: "midnight-oil-test-synthesis-source-packet",
    planned_synthesis_evidence_map_id: "midnight-oil-test-synthesis-evidence-map",
    planned_worker_id: "midnight-oil-test-runner-dispatch-worker",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    final_artifact_graph_commit_blockers: [
      "final artifact graph commit receipt writer",
      "graph transaction writer",
      "graph node commit writer",
      "graph edge set commit writer",
      "graph lineage index writer",
      "graph snapshot writer",
      "idempotent final artifact graph commit replay protection",
    ],
    required_final_artifact_graph_commit_invariants: [
      "final artifact graph commit planner must require final artifact persistence planning before any graph commit can be written",
      "final artifact graph commit planner must preserve source/evidence/citation lineage through the final artifact graph node, edge set, snapshot, and lineage index",
    ],
    required_final_artifact_graph_commit_receipt_fields: [
      "final_artifact_graph_commit_plan_receipt_id",
      "final_artifact_persistence_plan_receipt_id",
      "final_artifact_graph_commit_receipt_id",
      "graph_commit_id",
      "graph_transaction_id",
      "graph_node_id",
      "graph_edge_set_id",
      "graph_snapshot_id",
      "graph_lineage_index_id",
      "graph_commit_created",
      "idempotency_key",
    ],
    blocker_reason: "final_artifact_graph_commit_unimplemented",
    final_artifact_graph_commit_allowed: false,
    graph_commit_created: false,
    graph_transaction_created: false,
    graph_node_committed: false,
    graph_edge_set_committed: false,
    graph_snapshot_created: false,
    graph_lineage_index_created: false,
    final_artifact_persistence_allowed: false,
    final_artifact_persisted: false,
    information_asset_created: false,
    hosted_html_asset_created: false,
    artifact_ledger_entry_created: false,
    graph_node_created: false,
    graph_edge_set_created: false,
    final_html_artifact_assembled: false,
    final_synthesis_draft_created: false,
    synthesis_bundle_assembled: false,
    worker_output_aggregated: false,
    worker_started: false,
    scheduler_job_created: false,
    runner_dispatch_enqueued: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    adapter_plan_notes: [
      "final artifact graph commit plan only: no graph transaction, node commit, edge set, snapshot, lineage index, hosted asset, or final artifact is created",
    ],
  })),
  finalArtifactPublishPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-artifact-publish-plan",
    final_artifact_graph_commit_plan_receipt_id:
      "midnight-oil-test-final-artifact-graph-commit-plan",
    final_artifact_persistence_plan_receipt_id:
      "midnight-oil-test-final-artifact-persistence-plan",
    final_html_artifact_assembly_plan_receipt_id:
      "midnight-oil-test-final-html-artifact-assembly-plan",
    final_synthesis_draft_plan_receipt_id:
      "midnight-oil-test-final-synthesis-draft-plan",
    synthesis_bundle_assembly_plan_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-plan",
    worker_synthesis_handoff_plan_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_final_artifact_publish_unimplemented",
    adapter_key: "final_artifact_publish",
    planned_final_artifact_publish_receipt_id:
      "midnight-oil-test-final-artifact-publish-receipt",
    planned_publish_transaction_id:
      "midnight-oil-test-final-artifact-publish-transaction",
    planned_published_information_asset_id:
      "midnight-oil-test-published-information-asset",
    planned_account_visible_asset_id: "midnight-oil-test-account-visible-asset",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_twin_notes_workspace_entry_id:
      "midnight-oil-test-twin-notes-workspace-entry",
    planned_search_index_entry_id: "midnight-oil-test-search-index-entry",
    planned_share_policy_id: "midnight-oil-test-private-share-policy",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_operator_notification_id:
      "midnight-oil-test-final-artifact-publish-notification",
    planned_graph_commit_id: "midnight-oil-test-final-artifact-graph-commit",
    planned_graph_snapshot_id: "midnight-oil-test-final-artifact-graph-snapshot",
    planned_graph_lineage_index_id:
      "midnight-oil-test-final-artifact-graph-lineage-index",
    planned_information_asset_id: "midnight-oil-test-information-asset",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_final_html_artifact_id: "midnight-oil-test-final-html-artifact",
    planned_final_html_document_id: "midnight-oil-test-final-html-document",
    planned_synthesis_source_packet_id: "midnight-oil-test-synthesis-source-packet",
    planned_synthesis_evidence_map_id: "midnight-oil-test-synthesis-evidence-map",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    final_artifact_publish_blockers: [
      "final artifact publish receipt writer",
      "publish transaction writer",
      "account-visible asset writer",
      "reading workspace entry writer",
      "search index entry writer",
      "private read URL writer",
      "operator notification writer",
      "idempotent final artifact publish replay protection",
    ],
    required_final_artifact_publish_invariants: [
      "final artifact publish planner must require final artifact graph commit planning before any account-visible artifact can be published",
      "final artifact publish planner must preserve source/evidence/citation lineage through the reading workspace entry, search index entry, graph snapshot, and twin notes workspace entry",
    ],
    required_final_artifact_publish_receipt_fields: [
      "final_artifact_publish_plan_receipt_id",
      "final_artifact_graph_commit_plan_receipt_id",
      "final_artifact_publish_receipt_id",
      "publish_transaction_id",
      "published_information_asset_id",
      "account_visible_asset_id",
      "reading_workspace_entry_id",
      "search_index_entry_id",
      "private_read_url_id",
      "information_asset_published",
      "idempotency_key",
    ],
    blocker_reason: "final_artifact_publish_unimplemented",
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    twin_notes_workspace_entry_created: false,
    search_index_entry_created: false,
    share_policy_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    final_artifact_graph_commit_allowed: false,
    graph_commit_created: false,
    graph_transaction_created: false,
    graph_node_committed: false,
    graph_edge_set_committed: false,
    graph_snapshot_created: false,
    graph_lineage_index_created: false,
    final_artifact_persisted: false,
    information_asset_created: false,
    hosted_html_asset_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "final artifact publish plan only: no publish transaction, account-visible asset, workspace entry, search index entry, private read URL, notification, graph mutation, or final artifact is created",
    ],
  })),
  finalArtifactCompletionFinalizationPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    final_artifact_graph_commit_plan_receipt_id:
      "midnight-oil-test-final-artifact-graph-commit-plan",
    final_artifact_persistence_plan_receipt_id:
      "midnight-oil-test-final-artifact-persistence-plan",
    final_html_artifact_assembly_plan_receipt_id:
      "midnight-oil-test-final-html-artifact-assembly-plan",
    final_synthesis_draft_plan_receipt_id:
      "midnight-oil-test-final-synthesis-draft-plan",
    synthesis_bundle_assembly_plan_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-plan",
    worker_synthesis_handoff_plan_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_final_artifact_completion_finalization_unimplemented",
    adapter_key: "final_artifact_completion_finalization",
    planned_final_artifact_completion_receipt_id:
      "midnight-oil-test-final-artifact-completion-receipt",
    planned_final_artifact_finalization_receipt_id:
      "midnight-oil-test-final-artifact-finalization-receipt",
    planned_completion_record_id:
      "midnight-oil-test-final-artifact-completion-record",
    planned_finalization_transaction_id:
      "midnight-oil-test-final-artifact-finalization-transaction",
    planned_artifact_archive_manifest_id:
      "midnight-oil-test-final-artifact-archive-manifest",
    planned_operator_handoff_summary_id:
      "midnight-oil-test-final-artifact-operator-handoff-summary",
    planned_delivery_status_id: "midnight-oil-test-final-artifact-delivery-status",
    planned_quality_attestation_id:
      "midnight-oil-test-final-artifact-quality-attestation",
    planned_completion_audit_entry_id:
      "midnight-oil-test-final-artifact-completion-audit-entry",
    planned_publish_transaction_id:
      "midnight-oil-test-final-artifact-publish-transaction",
    planned_account_visible_asset_id: "midnight-oil-test-account-visible-asset",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_search_index_entry_id: "midnight-oil-test-search-index-entry",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_graph_commit_id: "midnight-oil-test-final-artifact-graph-commit",
    planned_graph_snapshot_id: "midnight-oil-test-final-artifact-graph-snapshot",
    planned_information_asset_id: "midnight-oil-test-information-asset",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    final_artifact_completion_finalization_blockers: [
      "final artifact completion receipt writer",
      "final artifact finalization transaction writer",
      "artifact archive manifest writer",
      "operator handoff summary writer",
      "delivery status finalizer",
      "quality attestation writer",
      "completion audit entry writer",
      "idempotent final artifact completion finalization replay protection",
    ],
    required_final_artifact_completion_finalization_invariants: [
      "final artifact completion finalization planner must require final artifact publish planning before any completion record can be written",
      "final artifact completion finalization planner must preserve source/evidence/citation lineage through archive manifest, operator handoff summary, quality attestation, and completion audit entry",
    ],
    required_final_artifact_completion_finalization_receipt_fields: [
      "final_artifact_completion_finalization_plan_receipt_id",
      "final_artifact_publish_plan_receipt_id",
      "final_artifact_completion_receipt_id",
      "final_artifact_finalization_receipt_id",
      "completion_record_id",
      "finalization_transaction_id",
      "artifact_archive_manifest_id",
      "operator_handoff_summary_id",
      "delivery_status_id",
      "quality_attestation_id",
      "completion_audit_entry_id",
      "idempotency_key",
    ],
    blocker_reason: "final_artifact_completion_finalization_unimplemented",
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "final artifact completion finalization plan only: no completion record, finalization transaction, archive manifest, handoff summary, delivery status, attestation, audit entry, graph mutation, or final artifact is created",
    ],
  })),
  finalRunClosurePlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    final_artifact_graph_commit_plan_receipt_id:
      "midnight-oil-test-final-artifact-graph-commit-plan",
    final_artifact_persistence_plan_receipt_id:
      "midnight-oil-test-final-artifact-persistence-plan",
    final_html_artifact_assembly_plan_receipt_id:
      "midnight-oil-test-final-html-artifact-assembly-plan",
    final_synthesis_draft_plan_receipt_id:
      "midnight-oil-test-final-synthesis-draft-plan",
    synthesis_bundle_assembly_plan_receipt_id:
      "midnight-oil-test-synthesis-bundle-assembly-plan",
    worker_synthesis_handoff_plan_receipt_id:
      "midnight-oil-test-worker-synthesis-handoff-plan",
    worker_output_aggregation_plan_receipt_id:
      "midnight-oil-test-worker-output-aggregation-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_final_run_closure_unimplemented",
    adapter_key: "final_run_closure",
    planned_final_run_closure_receipt_id: "midnight-oil-test-final-run-closure-receipt",
    planned_run_closeout_record_id: "midnight-oil-test-run-closeout-record",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_run_retention_manifest_id: "midnight-oil-test-run-retention-manifest",
    planned_billing_reconciliation_id: "midnight-oil-test-billing-reconciliation",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_final_artifact_completion_receipt_id:
      "midnight-oil-test-final-artifact-completion-receipt",
    planned_final_artifact_finalization_receipt_id:
      "midnight-oil-test-final-artifact-finalization-receipt",
    planned_completion_record_id:
      "midnight-oil-test-final-artifact-completion-record",
    planned_artifact_archive_manifest_id:
      "midnight-oil-test-final-artifact-archive-manifest",
    planned_operator_handoff_summary_id:
      "midnight-oil-test-final-artifact-operator-handoff-summary",
    planned_delivery_status_id: "midnight-oil-test-final-artifact-delivery-status",
    planned_quality_attestation_id:
      "midnight-oil-test-final-artifact-quality-attestation",
    planned_completion_audit_entry_id:
      "midnight-oil-test-final-artifact-completion-audit-entry",
    planned_account_visible_asset_id: "midnight-oil-test-account-visible-asset",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_search_index_entry_id: "midnight-oil-test-search-index-entry",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_graph_commit_id: "midnight-oil-test-final-artifact-graph-commit",
    planned_graph_snapshot_id: "midnight-oil-test-final-artifact-graph-snapshot",
    planned_information_asset_id: "midnight-oil-test-information-asset",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    final_run_closure_blockers: [
      "final run closure receipt writer",
      "run closeout record writer",
      "operator delivery ledger writer",
      "delivery notification dispatcher",
      "workspace delivery card writer",
      "run retention manifest writer",
      "billing reconciliation writer",
      "model usage rollup writer",
      "source lineage archive writer",
    ],
    required_final_run_closure_invariants: [
      "final run closure planner must require final artifact completion finalization planning before any run closeout can be written",
      "final run closure planner must preserve account-visible asset, private read URL, graph commit, hosted HTML asset, source/evidence lineage, and idempotency lineage through the operator delivery ledger entry",
    ],
    required_final_run_closure_receipt_fields: [
      "final_run_closure_plan_receipt_id",
      "final_artifact_completion_finalization_plan_receipt_id",
      "run_closeout_record_id",
      "operator_delivery_ledger_entry_id",
      "workspace_delivery_card_id",
      "model_usage_rollup_id",
      "source_lineage_archive_id",
      "idempotency_key",
    ],
    blocker_reason: "final_run_closure_unimplemented",
    final_run_closure_allowed: false,
    run_closeout_record_created: false,
    operator_delivery_ledger_entry_created: false,
    delivery_notification_created: false,
    workspace_delivery_card_created: false,
    run_retention_manifest_created: false,
    billing_reconciliation_created: false,
    model_usage_rollup_created: false,
    source_lineage_archive_created: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "final run closure plan only: no closeout record, operator delivery ledger entry, delivery notification, workspace card, retention manifest, billing reconciliation, model usage rollup, source lineage archive, or final artifact is created",
    ],
  })),
  operatorNotificationDeliveryReadinessPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_operator_notification_delivery_readiness_unimplemented",
    adapter_key: "operator_notification_delivery_readiness",
    planned_operator_notification_delivery_readiness_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-receipt",
    planned_operator_notification_dispatch_id:
      "midnight-oil-test-operator-notification-dispatch",
    planned_operator_notification_payload_id:
      "midnight-oil-test-operator-notification-payload",
    planned_operator_delivery_channel_policy_id:
      "midnight-oil-test-operator-delivery-channel-policy",
    planned_operator_notification_template_id:
      "midnight-oil-test-operator-notification-template",
    planned_operator_notification_audit_entry_id:
      "midnight-oil-test-operator-notification-audit-entry",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_run_closeout_record_id: "midnight-oil-test-run-closeout-record",
    planned_final_run_closure_receipt_id: "midnight-oil-test-final-run-closure-receipt",
    planned_account_visible_asset_id: "midnight-oil-test-account-visible-asset",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_quality_attestation_id:
      "midnight-oil-test-final-artifact-quality-attestation",
    planned_completion_audit_entry_id:
      "midnight-oil-test-final-artifact-completion-audit-entry",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    operator_notification_delivery_readiness_blockers: [
      "operator notification readiness receipt writer",
      "operator notification dispatch writer",
      "operator notification payload writer",
      "operator delivery channel policy writer",
      "operator notification template writer",
      "operator notification audit entry writer",
      "workspace delivery card notification binding writer",
      "operator delivery ledger notification binding writer",
    ],
    required_operator_notification_delivery_readiness_invariants: [
      "operator notification delivery readiness planner must require final run closure planning before any notification dispatch can be written",
      "operator notification delivery readiness planner must preserve private URL and account-visible delivery lineage without activating URLs or notifying operators during planning",
    ],
    required_operator_notification_delivery_readiness_receipt_fields: [
      "operator_notification_delivery_readiness_plan_receipt_id",
      "final_run_closure_plan_receipt_id",
      "operator_notification_dispatch_id",
      "operator_notification_payload_id",
      "operator_delivery_channel_policy_id",
      "operator_notification_audit_entry_id",
      "workspace_delivery_card_id",
      "operator_delivery_ledger_entry_id",
    ],
    blocker_reason: "operator_notification_delivery_readiness_unimplemented",
    operator_notification_delivery_readiness_allowed: false,
    operator_notification_dispatch_created: false,
    operator_notification_payload_created: false,
    operator_delivery_channel_policy_created: false,
    operator_notification_template_created: false,
    operator_notification_audit_entry_created: false,
    delivery_notification_created: false,
    workspace_delivery_card_created: false,
    operator_delivery_ledger_entry_created: false,
    run_closeout_record_created: false,
    final_run_closure_allowed: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "operator notification delivery readiness plan only: no notification dispatch, payload, channel policy, template, audit entry, workspace card binding, delivery ledger binding, URL activation, operator notification, or final artifact is created",
    ],
  })),
  operatorNotificationDeliveryApplyPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_operator_notification_delivery_apply_unimplemented",
    adapter_key: "operator_notification_delivery_apply",
    planned_operator_notification_delivery_apply_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-receipt",
    planned_operator_notification_delivery_transaction_id:
      "midnight-oil-test-operator-notification-delivery-transaction",
    planned_operator_notification_dispatch_id:
      "midnight-oil-test-operator-notification-dispatch",
    planned_operator_notification_payload_id:
      "midnight-oil-test-operator-notification-payload",
    planned_operator_delivery_channel_policy_id:
      "midnight-oil-test-operator-delivery-channel-policy",
    planned_operator_notification_template_id:
      "midnight-oil-test-operator-notification-template",
    planned_operator_notification_audit_entry_id:
      "midnight-oil-test-operator-notification-audit-entry",
    planned_operator_notification_delivery_attempt_id:
      "midnight-oil-test-operator-notification-delivery-attempt",
    planned_operator_notification_delivery_result_id:
      "midnight-oil-test-operator-notification-delivery-result",
    planned_operator_notification_delivery_status_id:
      "midnight-oil-test-operator-notification-delivery-status",
    planned_operator_notification_retry_policy_id:
      "midnight-oil-test-operator-notification-retry-policy",
    planned_operator_notification_dead_letter_id:
      "midnight-oil-test-operator-notification-dead-letter",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_run_closeout_record_id: "midnight-oil-test-run-closeout-record",
    planned_final_run_closure_receipt_id: "midnight-oil-test-final-run-closure-receipt",
    planned_account_visible_asset_id: "midnight-oil-test-account-visible-asset",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_quality_attestation_id:
      "midnight-oil-test-final-artifact-quality-attestation",
    planned_completion_audit_entry_id:
      "midnight-oil-test-final-artifact-completion-audit-entry",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    operator_notification_delivery_apply_blockers: [
      "operator notification delivery transaction writer",
      "operator notification delivery attempt writer",
      "operator notification delivery result writer",
      "operator notification retry policy writer",
      "operator notification dead-letter writer",
      "operator notification delivery channel adapter",
    ],
    required_operator_notification_delivery_apply_invariants: [
      "operator notification delivery apply planner must require notification readiness planning before any delivery transaction can be written",
      "operator notification delivery apply planner must preserve retry/dead-letter lineage without sending notifications, activating URLs, mutating delivery state, or marking delivery complete during planning",
    ],
    required_operator_notification_delivery_apply_receipt_fields: [
      "operator_notification_delivery_apply_plan_receipt_id",
      "operator_notification_delivery_readiness_plan_receipt_id",
      "operator_notification_delivery_transaction_id",
      "operator_notification_delivery_attempt_id",
      "operator_notification_delivery_result_id",
      "operator_notification_retry_policy_id",
      "operator_notification_dead_letter_id",
    ],
    blocker_reason: "operator_notification_delivery_apply_unimplemented",
    operator_notification_delivery_apply_allowed: false,
    operator_notification_delivery_transaction_created: false,
    operator_notification_dispatch_created: false,
    operator_notification_payload_created: false,
    operator_delivery_channel_policy_created: false,
    operator_notification_template_created: false,
    operator_notification_audit_entry_created: false,
    operator_notification_delivery_attempt_created: false,
    operator_notification_delivery_result_created: false,
    operator_notification_delivery_status_created: false,
    operator_notification_retry_policy_created: false,
    operator_notification_dead_letter_created: false,
    operator_notification_delivery_readiness_allowed: false,
    delivery_notification_created: false,
    workspace_delivery_card_created: false,
    operator_delivery_ledger_entry_created: false,
    run_closeout_record_created: false,
    final_run_closure_allowed: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "operator notification delivery apply plan only: no delivery transaction, notification dispatch, payload, attempt, result, status, retry, dead-letter, workspace card update, delivery ledger update, URL activation, operator notification, or final artifact is created",
    ],
  })),
  operatorNotificationDeliveryResultReconciliationPlanMidnightOil: vi.fn(async () => ({
    receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_operator_notification_delivery_result_reconciliation_unimplemented",
    adapter_key: "operator_notification_delivery_result_reconciliation",
    planned_operator_notification_delivery_result_reconciliation_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-receipt",
    planned_operator_notification_delivery_apply_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-receipt",
    planned_operator_notification_delivery_transaction_id:
      "midnight-oil-test-operator-notification-delivery-transaction",
    planned_operator_notification_dispatch_id:
      "midnight-oil-test-operator-notification-dispatch",
    planned_operator_notification_payload_id:
      "midnight-oil-test-operator-notification-payload",
    planned_operator_notification_delivery_attempt_id:
      "midnight-oil-test-operator-notification-delivery-attempt",
    planned_operator_notification_delivery_result_id:
      "midnight-oil-test-operator-notification-delivery-result",
    planned_operator_notification_delivery_status_id:
      "midnight-oil-test-operator-notification-delivery-status",
    planned_operator_notification_delivery_outcome_record_id:
      "midnight-oil-test-operator-notification-delivery-outcome-record",
    planned_operator_notification_delivery_reconciliation_entry_id:
      "midnight-oil-test-operator-notification-delivery-reconciliation-entry",
    planned_operator_notification_delivery_retry_policy_id:
      "midnight-oil-test-operator-notification-retry-policy",
    planned_operator_notification_delivery_retry_decision_id:
      "midnight-oil-test-operator-notification-delivery-retry-decision",
    planned_operator_notification_dead_letter_id:
      "midnight-oil-test-operator-notification-dead-letter",
    planned_operator_notification_dead_letter_entry_id:
      "midnight-oil-test-operator-notification-dead-letter-entry",
    planned_operator_notification_audit_entry_id:
      "midnight-oil-test-operator-notification-audit-entry",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_run_closeout_record_id: "midnight-oil-test-run-closeout-record",
    planned_final_run_closure_receipt_id: "midnight-oil-test-final-run-closure-receipt",
    planned_account_visible_asset_id: "midnight-oil-test-account-visible-asset",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_quality_attestation_id:
      "midnight-oil-test-final-artifact-quality-attestation",
    planned_completion_audit_entry_id:
      "midnight-oil-test-final-artifact-completion-audit-entry",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    operator_notification_delivery_result_reconciliation_blockers: [
      "operator notification delivery outcome record writer",
      "operator notification delivery reconciliation entry writer",
      "operator notification delivery retry decision writer",
      "operator notification dead-letter entry writer",
      "operator delivery ledger result reconciliation writer",
    ],
    required_operator_notification_delivery_result_reconciliation_invariants: [
      "operator notification delivery result reconciliation planner must require delivery apply planning before any delivery outcome can be reconciled",
      "operator notification delivery result reconciliation planner must preserve retry/dead-letter lineage without retrying, sending notifications, activating URLs, mutating delivery state, or marking delivery complete during planning",
    ],
    required_operator_notification_delivery_result_reconciliation_receipt_fields: [
      "operator_notification_delivery_result_reconciliation_plan_receipt_id",
      "operator_notification_delivery_apply_plan_receipt_id",
      "operator_notification_delivery_outcome_record_id",
      "operator_notification_delivery_reconciliation_entry_id",
      "operator_notification_delivery_retry_decision_id",
      "operator_notification_dead_letter_entry_id",
    ],
    blocker_reason: "operator_notification_delivery_result_reconciliation_unimplemented",
    operator_notification_delivery_result_reconciliation_allowed: false,
    operator_notification_delivery_outcome_record_created: false,
    operator_notification_delivery_reconciliation_entry_created: false,
    operator_notification_delivery_retry_decision_created: false,
    operator_notification_dead_letter_entry_created: false,
    operator_notification_delivery_apply_allowed: false,
    operator_notification_delivery_transaction_created: false,
    operator_notification_dispatch_created: false,
    operator_notification_payload_created: false,
    operator_delivery_channel_policy_created: false,
    operator_notification_template_created: false,
    operator_notification_audit_entry_created: false,
    operator_notification_delivery_attempt_created: false,
    operator_notification_delivery_result_created: false,
    operator_notification_delivery_status_created: false,
    operator_notification_retry_policy_created: false,
    operator_notification_dead_letter_created: false,
    operator_notification_delivery_readiness_allowed: false,
    delivery_notification_created: false,
    workspace_delivery_card_created: false,
    operator_delivery_ledger_entry_created: false,
    run_closeout_record_created: false,
    final_run_closure_allowed: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "operator notification delivery result reconciliation plan only: no outcome record, reconciliation entry, retry decision, dead-letter entry, delivery transaction, dispatch, payload, attempt, result, status, URL activation, operator notification, or final artifact is created",
    ],
  })),
  operatorDeliveryLedgerReconciliationPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_operator_delivery_ledger_reconciliation_unimplemented",
    adapter_key: "operator_delivery_ledger_reconciliation",
    planned_operator_delivery_ledger_reconciliation_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-receipt",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_operator_delivery_ledger_result_entry_id:
      "midnight-oil-test-operator-delivery-ledger-result-entry",
    planned_operator_delivery_ledger_status_entry_id:
      "midnight-oil-test-operator-delivery-ledger-status-entry",
    planned_operator_delivery_ledger_retry_entry_id:
      "midnight-oil-test-operator-delivery-ledger-retry-entry",
    planned_operator_delivery_ledger_dead_letter_entry_id:
      "midnight-oil-test-operator-delivery-ledger-dead-letter-entry",
    planned_operator_notification_delivery_result_reconciliation_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-receipt",
    planned_operator_notification_delivery_outcome_record_id:
      "midnight-oil-test-operator-notification-delivery-outcome-record",
    planned_operator_notification_delivery_reconciliation_entry_id:
      "midnight-oil-test-operator-notification-delivery-reconciliation-entry",
    planned_operator_notification_delivery_retry_decision_id:
      "midnight-oil-test-operator-notification-delivery-retry-decision",
    planned_operator_notification_dead_letter_entry_id:
      "midnight-oil-test-operator-notification-dead-letter-entry",
    planned_operator_notification_delivery_apply_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-receipt",
    planned_operator_notification_delivery_transaction_id:
      "midnight-oil-test-operator-notification-delivery-transaction",
    planned_operator_notification_dispatch_id:
      "midnight-oil-test-operator-notification-dispatch",
    planned_operator_notification_payload_id:
      "midnight-oil-test-operator-notification-payload",
    planned_operator_notification_delivery_attempt_id:
      "midnight-oil-test-operator-notification-delivery-attempt",
    planned_operator_notification_delivery_result_id:
      "midnight-oil-test-operator-notification-delivery-result",
    planned_operator_notification_delivery_status_id:
      "midnight-oil-test-operator-notification-delivery-status",
    planned_operator_notification_delivery_retry_policy_id:
      "midnight-oil-test-operator-notification-retry-policy",
    planned_operator_notification_dead_letter_id:
      "midnight-oil-test-operator-notification-dead-letter",
    planned_operator_notification_audit_entry_id:
      "midnight-oil-test-operator-notification-audit-entry",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_run_closeout_record_id: "midnight-oil-test-run-closeout-record",
    planned_final_run_closure_receipt_id: "midnight-oil-test-final-run-closure-receipt",
    planned_account_visible_asset_id: "midnight-oil-test-account-visible-asset",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_quality_attestation_id:
      "midnight-oil-test-final-artifact-quality-attestation",
    planned_completion_audit_entry_id:
      "midnight-oil-test-final-artifact-completion-audit-entry",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_runner_dispatch_id: "midnight-oil-test-midnight-oil-runner-dispatch",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    operator_delivery_ledger_reconciliation_blockers: [
      "operator delivery ledger reconciliation receipt writer",
      "operator delivery ledger result entry writer",
      "operator delivery ledger status entry writer",
      "operator delivery ledger retry entry writer",
      "operator delivery ledger dead-letter entry writer",
    ],
    required_operator_delivery_ledger_reconciliation_invariants: [
      "operator delivery ledger reconciliation planner must require notification delivery result reconciliation planning before ledger rows can be reconciled",
      "operator delivery ledger reconciliation planner must keep ledger reconciliation rows uncreated until a real delivery outcome record and reconciliation entry exist",
    ],
    required_operator_delivery_ledger_reconciliation_receipt_fields: [
      "operator_delivery_ledger_reconciliation_plan_receipt_id",
      "operator_notification_delivery_result_reconciliation_plan_receipt_id",
      "operator_delivery_ledger_result_entry_id",
      "operator_delivery_ledger_status_entry_id",
      "operator_delivery_ledger_retry_entry_id",
      "operator_delivery_ledger_dead_letter_entry_id",
    ],
    blocker_reason: "operator_delivery_ledger_reconciliation_unimplemented",
    operator_delivery_ledger_reconciliation_allowed: false,
    operator_delivery_ledger_result_entry_created: false,
    operator_delivery_ledger_status_entry_created: false,
    operator_delivery_ledger_retry_entry_created: false,
    operator_delivery_ledger_dead_letter_entry_created: false,
    operator_notification_delivery_result_reconciliation_allowed: false,
    operator_notification_delivery_outcome_record_created: false,
    operator_notification_delivery_reconciliation_entry_created: false,
    operator_notification_delivery_retry_decision_created: false,
    operator_notification_dead_letter_entry_created: false,
    operator_notification_delivery_apply_allowed: false,
    operator_notification_delivery_transaction_created: false,
    operator_notification_dispatch_created: false,
    operator_notification_payload_created: false,
    operator_delivery_channel_policy_created: false,
    operator_notification_template_created: false,
    operator_notification_audit_entry_created: false,
    operator_notification_delivery_attempt_created: false,
    operator_notification_delivery_result_created: false,
    operator_notification_delivery_status_created: false,
    operator_notification_retry_policy_created: false,
    operator_notification_dead_letter_created: false,
    operator_notification_delivery_readiness_allowed: false,
    delivery_notification_created: false,
    workspace_delivery_card_created: false,
    operator_delivery_ledger_entry_created: false,
    run_closeout_record_created: false,
    final_run_closure_allowed: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "operator delivery ledger reconciliation plan only: no ledger entry, ledger result entry, ledger status entry, ledger retry entry, ledger dead-letter entry, outcome record, delivery transaction, dispatch, URL activation, operator notification, or final artifact is created",
    ],
  })),
  workspaceDeliveryCardReconciliationPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
    operator_delivery_ledger_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_workspace_delivery_card_reconciliation_unimplemented",
    adapter_key: "workspace_delivery_card_reconciliation",
    planned_workspace_delivery_card_reconciliation_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-receipt",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_workspace_delivery_card_result_entry_id:
      "midnight-oil-test-workspace-delivery-card-result-entry",
    planned_workspace_delivery_card_status_entry_id:
      "midnight-oil-test-workspace-delivery-card-status-entry",
    planned_workspace_delivery_card_notification_entry_id:
      "midnight-oil-test-workspace-delivery-card-notification-entry",
    planned_workspace_delivery_card_replay_guard_id:
      "midnight-oil-test-workspace-delivery-card-replay-guard",
    planned_operator_delivery_ledger_reconciliation_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-receipt",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_operator_delivery_ledger_result_entry_id:
      "midnight-oil-test-operator-delivery-ledger-result-entry",
    planned_operator_delivery_ledger_status_entry_id:
      "midnight-oil-test-operator-delivery-ledger-status-entry",
    planned_operator_delivery_ledger_retry_entry_id:
      "midnight-oil-test-operator-delivery-ledger-retry-entry",
    planned_operator_delivery_ledger_dead_letter_entry_id:
      "midnight-oil-test-operator-delivery-ledger-dead-letter-entry",
    planned_operator_notification_delivery_outcome_record_id:
      "midnight-oil-test-operator-notification-delivery-outcome-record",
    planned_operator_notification_delivery_reconciliation_entry_id:
      "midnight-oil-test-operator-notification-delivery-reconciliation-entry",
    planned_operator_notification_delivery_retry_decision_id:
      "midnight-oil-test-operator-notification-delivery-retry-decision",
    planned_operator_notification_dead_letter_entry_id:
      "midnight-oil-test-operator-notification-dead-letter-entry",
    planned_operator_notification_delivery_result_id:
      "midnight-oil-test-operator-notification-delivery-result",
    planned_operator_notification_delivery_status_id:
      "midnight-oil-test-operator-notification-delivery-status",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    workspace_delivery_card_reconciliation_blockers: [
      "workspace delivery card reconciliation receipt writer",
      "workspace delivery card result entry writer",
      "workspace delivery card status entry writer",
      "workspace delivery card notification entry writer",
      "workspace delivery card replay guard",
    ],
    required_workspace_delivery_card_reconciliation_invariants: [
      "workspace delivery card reconciliation planner must require operator delivery ledger reconciliation planning before workspace delivery cards can be reconciled",
      "workspace delivery card reconciliation planner must keep workspace delivery card rows uncreated until real delivery ledger reconciliation rows exist",
    ],
    required_workspace_delivery_card_reconciliation_receipt_fields: [
      "workspace_delivery_card_reconciliation_plan_receipt_id",
      "operator_delivery_ledger_reconciliation_plan_receipt_id",
      "workspace_delivery_card_result_entry_id",
      "workspace_delivery_card_status_entry_id",
      "workspace_delivery_card_notification_entry_id",
      "workspace_delivery_card_replay_guard_id",
    ],
    blocker_reason: "workspace_delivery_card_reconciliation_unimplemented",
    workspace_delivery_card_reconciliation_allowed: false,
    workspace_delivery_card_result_entry_created: false,
    workspace_delivery_card_status_entry_created: false,
    workspace_delivery_card_notification_entry_created: false,
    workspace_delivery_card_created: false,
    operator_delivery_ledger_reconciliation_allowed: false,
    operator_delivery_ledger_result_entry_created: false,
    operator_delivery_ledger_status_entry_created: false,
    operator_delivery_ledger_retry_entry_created: false,
    operator_delivery_ledger_dead_letter_entry_created: false,
    operator_delivery_ledger_entry_created: false,
    operator_notification_delivery_result_reconciliation_allowed: false,
    operator_notification_delivery_outcome_record_created: false,
    operator_notification_delivery_reconciliation_entry_created: false,
    operator_notification_delivery_retry_decision_created: false,
    operator_notification_dead_letter_entry_created: false,
    operator_notification_delivery_apply_allowed: false,
    operator_notification_delivery_transaction_created: false,
    operator_notification_dispatch_created: false,
    operator_notification_payload_created: false,
    operator_delivery_channel_policy_created: false,
    operator_notification_template_created: false,
    operator_notification_audit_entry_created: false,
    operator_notification_delivery_attempt_created: false,
    operator_notification_delivery_result_created: false,
    operator_notification_delivery_status_created: false,
    operator_notification_retry_policy_created: false,
    operator_notification_dead_letter_created: false,
    operator_notification_delivery_readiness_allowed: false,
    delivery_notification_created: false,
    run_closeout_record_created: false,
    final_run_closure_allowed: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "workspace delivery card reconciliation plan only: no workspace card, card result entry, card status entry, card notification entry, ledger entry, delivery transaction, URL activation, operator notification, or final artifact is created",
    ],
  })),
  deliveryNotificationReconciliationPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-delivery-notification-reconciliation-plan",
    workspace_delivery_card_reconciliation_plan_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
    operator_delivery_ledger_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_delivery_notification_reconciliation_unimplemented",
    adapter_key: "delivery_notification_reconciliation",
    planned_delivery_notification_reconciliation_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-receipt",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_delivery_notification_status_entry_id:
      "midnight-oil-test-delivery-notification-status-entry",
    planned_delivery_notification_result_entry_id:
      "midnight-oil-test-delivery-notification-result-entry",
    planned_delivery_notification_operator_visible_event_id:
      "midnight-oil-test-delivery-notification-operator-visible-event",
    planned_delivery_notification_replay_guard_id:
      "midnight-oil-test-delivery-notification-replay-guard",
    planned_workspace_delivery_card_reconciliation_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-receipt",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_workspace_delivery_card_result_entry_id:
      "midnight-oil-test-workspace-delivery-card-result-entry",
    planned_workspace_delivery_card_status_entry_id:
      "midnight-oil-test-workspace-delivery-card-status-entry",
    planned_workspace_delivery_card_notification_entry_id:
      "midnight-oil-test-workspace-delivery-card-notification-entry",
    planned_workspace_delivery_card_replay_guard_id:
      "midnight-oil-test-workspace-delivery-card-replay-guard",
    planned_operator_delivery_ledger_reconciliation_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-receipt",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_operator_delivery_ledger_result_entry_id:
      "midnight-oil-test-operator-delivery-ledger-result-entry",
    planned_operator_delivery_ledger_status_entry_id:
      "midnight-oil-test-operator-delivery-ledger-status-entry",
    planned_operator_delivery_ledger_retry_entry_id:
      "midnight-oil-test-operator-delivery-ledger-retry-entry",
    planned_operator_delivery_ledger_dead_letter_entry_id:
      "midnight-oil-test-operator-delivery-ledger-dead-letter-entry",
    planned_operator_notification_delivery_outcome_record_id:
      "midnight-oil-test-operator-notification-delivery-outcome-record",
    planned_operator_notification_delivery_reconciliation_entry_id:
      "midnight-oil-test-operator-notification-delivery-reconciliation-entry",
    planned_operator_notification_delivery_retry_decision_id:
      "midnight-oil-test-operator-notification-delivery-retry-decision",
    planned_operator_notification_dead_letter_entry_id:
      "midnight-oil-test-operator-notification-dead-letter-entry",
    planned_operator_notification_delivery_result_id:
      "midnight-oil-test-operator-notification-delivery-result",
    planned_operator_notification_delivery_status_id:
      "midnight-oil-test-operator-notification-delivery-status",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    delivery_notification_reconciliation_blockers: [
      "delivery notification reconciliation receipt writer",
      "delivery notification status entry writer",
      "delivery notification result entry writer",
      "delivery notification operator visible event writer",
      "delivery notification replay guard",
    ],
    required_delivery_notification_reconciliation_invariants: [
      "delivery notification reconciliation planner must require workspace delivery card reconciliation planning before delivery notifications can be reconciled",
      "delivery notification reconciliation planner must keep notification rows uncreated until real workspace card and delivery ledger reconciliation rows exist",
    ],
    required_delivery_notification_reconciliation_receipt_fields: [
      "delivery_notification_reconciliation_plan_receipt_id",
      "workspace_delivery_card_reconciliation_plan_receipt_id",
      "delivery_notification_status_entry_id",
      "delivery_notification_result_entry_id",
      "delivery_notification_operator_visible_event_id",
      "delivery_notification_replay_guard_id",
    ],
    blocker_reason: "delivery_notification_reconciliation_unimplemented",
    delivery_notification_reconciliation_allowed: false,
    delivery_notification_status_entry_created: false,
    delivery_notification_result_entry_created: false,
    delivery_notification_operator_visible_event_created: false,
    delivery_notification_created: false,
    workspace_delivery_card_reconciliation_allowed: false,
    workspace_delivery_card_result_entry_created: false,
    workspace_delivery_card_status_entry_created: false,
    workspace_delivery_card_notification_entry_created: false,
    workspace_delivery_card_created: false,
    operator_delivery_ledger_reconciliation_allowed: false,
    operator_delivery_ledger_result_entry_created: false,
    operator_delivery_ledger_status_entry_created: false,
    operator_delivery_ledger_retry_entry_created: false,
    operator_delivery_ledger_dead_letter_entry_created: false,
    operator_delivery_ledger_entry_created: false,
    operator_notification_delivery_result_reconciliation_allowed: false,
    operator_notification_delivery_outcome_record_created: false,
    operator_notification_delivery_reconciliation_entry_created: false,
    operator_notification_delivery_retry_decision_created: false,
    operator_notification_dead_letter_entry_created: false,
    operator_notification_delivery_apply_allowed: false,
    operator_notification_delivery_transaction_created: false,
    operator_notification_dispatch_created: false,
    operator_notification_payload_created: false,
    operator_delivery_channel_policy_created: false,
    operator_notification_template_created: false,
    operator_notification_audit_entry_created: false,
    operator_notification_delivery_attempt_created: false,
    operator_notification_delivery_result_created: false,
    operator_notification_delivery_status_created: false,
    operator_notification_retry_policy_created: false,
    operator_notification_dead_letter_created: false,
    operator_notification_delivery_readiness_allowed: false,
    run_closeout_record_created: false,
    final_run_closure_allowed: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "delivery notification reconciliation plan only: no delivery notification, status entry, result entry, operator visible event, workspace card, ledger entry, URL activation, operator notification, or final artifact is created",
    ],
  })),
  retentionBillingReconciliationPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-retention-billing-reconciliation-plan",
    delivery_notification_reconciliation_plan_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-plan",
    workspace_delivery_card_reconciliation_plan_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
    operator_delivery_ledger_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_retention_billing_reconciliation_unimplemented",
    adapter_key: "retention_billing_reconciliation",
    planned_retention_billing_reconciliation_receipt_id:
      "midnight-oil-test-retention-billing-reconciliation-receipt",
    planned_run_retention_manifest_id: "midnight-oil-test-run-retention-manifest",
    planned_billing_reconciliation_id: "midnight-oil-test-billing-reconciliation",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_run_retention_manifest_status_entry_id:
      "midnight-oil-test-run-retention-manifest-status-entry",
    planned_billing_reconciliation_status_entry_id:
      "midnight-oil-test-billing-reconciliation-status-entry",
    planned_model_usage_rollup_reconciliation_entry_id:
      "midnight-oil-test-model-usage-rollup-reconciliation-entry",
    planned_source_lineage_archive_reconciliation_entry_id:
      "midnight-oil-test-source-lineage-archive-reconciliation-entry",
    planned_delivery_notification_reconciliation_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-receipt",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_delivery_notification_status_entry_id:
      "midnight-oil-test-delivery-notification-status-entry",
    planned_delivery_notification_result_entry_id:
      "midnight-oil-test-delivery-notification-result-entry",
    planned_delivery_notification_operator_visible_event_id:
      "midnight-oil-test-delivery-notification-operator-visible-event",
    planned_delivery_notification_replay_guard_id:
      "midnight-oil-test-delivery-notification-replay-guard",
    planned_workspace_delivery_card_reconciliation_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-receipt",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_operator_delivery_ledger_reconciliation_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-receipt",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_operator_delivery_ledger_status_entry_id:
      "midnight-oil-test-operator-delivery-ledger-status-entry",
    planned_operator_notification_delivery_outcome_record_id:
      "midnight-oil-test-operator-notification-delivery-outcome-record",
    planned_operator_notification_delivery_reconciliation_entry_id:
      "midnight-oil-test-operator-notification-delivery-reconciliation-entry",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_reading_workspace_entry_id: "midnight-oil-test-reading-workspace-entry",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    retention_billing_reconciliation_blockers: [
      "run retention manifest reconciliation receipt writer",
      "run retention manifest status entry writer",
      "billing reconciliation receipt writer",
      "billing reconciliation status entry writer",
      "model usage rollup reconciliation writer",
      "source lineage archive reconciliation writer",
      "retention and billing replay guard",
    ],
    required_retention_billing_reconciliation_invariants: [
      "retention billing reconciliation planner must require delivery notification reconciliation planning before retention, billing, usage, or source lineage rows can be reconciled",
      "retention billing reconciliation planner must keep retention, billing, usage, and source lineage rows uncreated until real delivery notification reconciliation rows exist",
    ],
    required_retention_billing_reconciliation_receipt_fields: [
      "retention_billing_reconciliation_plan_receipt_id",
      "delivery_notification_reconciliation_plan_receipt_id",
      "run_retention_manifest_id",
      "billing_reconciliation_id",
      "model_usage_rollup_reconciliation_entry_id",
      "source_lineage_archive_reconciliation_entry_id",
    ],
    blocker_reason: "retention_billing_reconciliation_unimplemented",
    retention_billing_reconciliation_allowed: false,
    run_retention_manifest_created: false,
    billing_reconciliation_created: false,
    model_usage_rollup_created: false,
    source_lineage_archive_created: false,
    run_retention_manifest_status_entry_created: false,
    billing_reconciliation_status_entry_created: false,
    model_usage_rollup_reconciliation_entry_created: false,
    source_lineage_archive_reconciliation_entry_created: false,
    delivery_notification_reconciliation_allowed: false,
    delivery_notification_status_entry_created: false,
    delivery_notification_result_entry_created: false,
    delivery_notification_operator_visible_event_created: false,
    delivery_notification_created: false,
    workspace_delivery_card_reconciliation_allowed: false,
    workspace_delivery_card_result_entry_created: false,
    workspace_delivery_card_status_entry_created: false,
    workspace_delivery_card_notification_entry_created: false,
    workspace_delivery_card_created: false,
    operator_delivery_ledger_reconciliation_allowed: false,
    operator_delivery_ledger_result_entry_created: false,
    operator_delivery_ledger_status_entry_created: false,
    operator_delivery_ledger_retry_entry_created: false,
    operator_delivery_ledger_dead_letter_entry_created: false,
    operator_delivery_ledger_entry_created: false,
    operator_notification_delivery_result_reconciliation_allowed: false,
    operator_notification_delivery_outcome_record_created: false,
    operator_notification_delivery_reconciliation_entry_created: false,
    operator_notification_delivery_retry_decision_created: false,
    operator_notification_dead_letter_entry_created: false,
    operator_notification_delivery_apply_allowed: false,
    operator_notification_delivery_transaction_created: false,
    operator_notification_dispatch_created: false,
    operator_notification_payload_created: false,
    operator_delivery_channel_policy_created: false,
    operator_notification_template_created: false,
    operator_notification_audit_entry_created: false,
    operator_notification_delivery_attempt_created: false,
    operator_notification_delivery_result_created: false,
    operator_notification_delivery_status_created: false,
    operator_notification_retry_policy_created: false,
    operator_notification_dead_letter_created: false,
    operator_notification_delivery_readiness_allowed: false,
    run_closeout_record_created: false,
    final_run_closure_allowed: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "retention billing reconciliation plan only: no retention manifest, billing reconciliation, model usage rollup, source lineage archive, delivery notification, workspace card, ledger entry, URL activation, operator notification, or final artifact is created",
    ],
  })),
  finalCloseoutArchiveReconciliationPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-final-closeout-archive-reconciliation-plan",
    retention_billing_reconciliation_plan_receipt_id:
      "midnight-oil-test-retention-billing-reconciliation-plan",
    delivery_notification_reconciliation_plan_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-plan",
    workspace_delivery_card_reconciliation_plan_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
    operator_delivery_ledger_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_final_closeout_archive_reconciliation_unimplemented",
    adapter_key: "final_closeout_archive_reconciliation",
    planned_final_closeout_archive_reconciliation_receipt_id:
      "midnight-oil-test-final-closeout-archive-reconciliation-receipt",
    planned_final_run_closure_receipt_id:
      "midnight-oil-test-final-run-closure-receipt",
    planned_run_closeout_record_id: "midnight-oil-test-run-closeout-record",
    planned_artifact_archive_manifest_id:
      "midnight-oil-test-final-artifact-archive-manifest",
    planned_operator_handoff_summary_id:
      "midnight-oil-test-operator-handoff-summary",
    planned_quality_attestation_id: "midnight-oil-test-quality-attestation",
    planned_completion_audit_entry_id:
      "midnight-oil-test-completion-audit-entry",
    planned_retention_billing_reconciliation_receipt_id:
      "midnight-oil-test-retention-billing-reconciliation-receipt",
    planned_run_retention_manifest_id: "midnight-oil-test-run-retention-manifest",
    planned_billing_reconciliation_id: "midnight-oil-test-billing-reconciliation",
    planned_model_usage_rollup_id: "midnight-oil-test-model-usage-rollup",
    planned_source_lineage_archive_id: "midnight-oil-test-source-lineage-archive",
    planned_source_lineage_archive_reconciliation_entry_id:
      "midnight-oil-test-source-lineage-archive-reconciliation-entry",
    planned_delivery_notification_reconciliation_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-receipt",
    planned_delivery_notification_id: "midnight-oil-test-delivery-notification",
    planned_workspace_delivery_card_id: "midnight-oil-test-workspace-delivery-card",
    planned_operator_delivery_ledger_entry_id:
      "midnight-oil-test-operator-delivery-ledger-entry",
    planned_private_read_url_id: "midnight-oil-test-private-read-url",
    planned_hosted_html_asset_id: "midnight-oil-test-hosted-html-asset",
    planned_idempotency_key: "midnight-oil-test-live-dispatch-final-enable-idempotency-key",
    final_closeout_archive_reconciliation_blockers: [
      "final closeout archive reconciliation receipt writer",
      "final run closure receipt reconciliation writer",
      "run closeout record reconciliation writer",
      "artifact archive manifest reconciliation writer",
      "operator handoff summary reconciliation writer",
      "quality attestation reconciliation writer",
      "completion audit reconciliation writer",
      "final closeout archive replay guard",
    ],
    required_final_closeout_archive_reconciliation_invariants: [
      "final closeout archive reconciliation planner must require retention billing reconciliation planning before closeout archive rows can be reconciled",
      "final closeout archive reconciliation planner must keep closeout archive rows uncreated until real retention, billing, usage, source lineage, delivery notification, workspace card, and ledger reconciliation rows exist",
    ],
    required_final_closeout_archive_reconciliation_receipt_fields: [
      "final_closeout_archive_reconciliation_plan_receipt_id",
      "retention_billing_reconciliation_plan_receipt_id",
      "final_closeout_archive_reconciliation_receipt_id",
      "final_run_closure_receipt_id",
      "run_closeout_record_id",
      "artifact_archive_manifest_id",
      "operator_handoff_summary_id",
      "quality_attestation_id",
      "completion_audit_entry_id",
    ],
    blocker_reason: "final_closeout_archive_reconciliation_unimplemented",
    final_closeout_archive_reconciliation_allowed: false,
    final_run_closure_receipt_reconciled: false,
    run_closeout_record_reconciled: false,
    artifact_archive_manifest_reconciled: false,
    operator_handoff_summary_reconciled: false,
    quality_attestation_reconciled: false,
    completion_audit_entry_reconciled: false,
    retention_billing_reconciliation_allowed: false,
    run_retention_manifest_created: false,
    billing_reconciliation_created: false,
    model_usage_rollup_created: false,
    source_lineage_archive_created: false,
    run_retention_manifest_status_entry_created: false,
    billing_reconciliation_status_entry_created: false,
    model_usage_rollup_reconciliation_entry_created: false,
    source_lineage_archive_reconciliation_entry_created: false,
    delivery_notification_reconciliation_allowed: false,
    delivery_notification_status_entry_created: false,
    delivery_notification_result_entry_created: false,
    delivery_notification_operator_visible_event_created: false,
    delivery_notification_created: false,
    workspace_delivery_card_reconciliation_allowed: false,
    workspace_delivery_card_result_entry_created: false,
    workspace_delivery_card_status_entry_created: false,
    workspace_delivery_card_notification_entry_created: false,
    workspace_delivery_card_created: false,
    operator_delivery_ledger_reconciliation_allowed: false,
    operator_delivery_ledger_result_entry_created: false,
    operator_delivery_ledger_status_entry_created: false,
    operator_delivery_ledger_retry_entry_created: false,
    operator_delivery_ledger_dead_letter_entry_created: false,
    operator_delivery_ledger_entry_created: false,
    run_closeout_record_created: false,
    final_run_closure_allowed: false,
    final_artifact_completion_finalization_allowed: false,
    completion_record_created: false,
    finalization_transaction_created: false,
    artifact_archive_manifest_created: false,
    operator_handoff_summary_created: false,
    delivery_status_marked_complete: false,
    quality_attestation_created: false,
    completion_audit_entry_created: false,
    final_artifact_publish_allowed: false,
    publish_transaction_created: false,
    information_asset_published: false,
    account_visible_asset_created: false,
    reading_workspace_entry_created: false,
    search_index_entry_created: false,
    private_read_url_created: false,
    operator_notification_created: false,
    graph_commit_created: false,
    graph_mutated: false,
    final_artifact_created: false,
    dispatch_performed: false,
    budget_reserved: false,
    provider_calls_made: false,
    retrieval_performed: false,
    source_receipts_created: false,
    adapter_plan_notes: [
      "final closeout archive reconciliation plan only: no final run closure receipt, run closeout record, archive manifest, handoff summary, quality attestation, completion audit, retention manifest, billing reconciliation, model usage rollup, source lineage archive, notification, URL activation, or final artifact is created",
    ],
  })),
  operatorArchiveHandoffPackagePlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-operator-archive-handoff-package-plan",
    final_closeout_archive_reconciliation_plan_receipt_id:
      "midnight-oil-test-final-closeout-archive-reconciliation-plan",
    retention_billing_reconciliation_plan_receipt_id:
      "midnight-oil-test-retention-billing-reconciliation-plan",
    delivery_notification_reconciliation_plan_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-plan",
    workspace_delivery_card_reconciliation_plan_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
    operator_delivery_ledger_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_operator_archive_handoff_package_unimplemented",
    adapter_key: "operator_archive_handoff_package",
    planned_operator_archive_handoff_package_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-receipt",
    planned_operator_archive_package_id:
      "midnight-oil-test-operator-archive-package",
    planned_operator_archive_manifest_id:
      "midnight-oil-test-operator-archive-manifest",
    planned_operator_handoff_bundle_id:
      "midnight-oil-test-operator-handoff-bundle",
    planned_final_closeout_archive_reconciliation_receipt_id:
      "midnight-oil-test-final-closeout-archive-reconciliation-receipt",
    planned_artifact_archive_manifest_id:
      "midnight-oil-test-final-artifact-archive-manifest",
    planned_operator_handoff_summary_id:
      "midnight-oil-test-operator-handoff-summary",
    operator_archive_handoff_package_blockers: [
      "operator archive handoff package receipt writer",
      "operator archive package writer",
      "operator archive manifest writer",
      "operator handoff bundle writer",
      "operator archive handoff package replay guard",
    ],
    required_operator_archive_handoff_package_invariants: [
      "operator archive handoff package planner must require final closeout archive reconciliation planning before operator archive handoff packages can be written",
    ],
    required_operator_archive_handoff_package_receipt_fields: [
      "operator_archive_handoff_package_plan_receipt_id",
      "final_closeout_archive_reconciliation_plan_receipt_id",
      "operator_archive_manifest_id",
      "operator_handoff_bundle_id",
      "artifact_archive_manifest_id",
      "operator_handoff_summary_id",
    ],
    blocker_reason: "operator_archive_handoff_package_unimplemented",
    operator_archive_handoff_package_allowed: false,
    operator_archive_package_created: false,
    operator_archive_manifest_created: false,
    operator_handoff_bundle_created: false,
    final_closeout_archive_reconciliation_allowed: false,
    final_run_closure_receipt_reconciled: false,
    run_closeout_record_reconciled: false,
    artifact_archive_manifest_reconciled: false,
    operator_handoff_summary_reconciled: false,
    quality_attestation_reconciled: false,
    completion_audit_entry_reconciled: false,
    retention_billing_reconciliation_allowed: false,
    adapter_plan_notes: [
      "operator archive handoff package plan only: no operator archive package, operator archive manifest, handoff bundle, final closeout archive reconciliation receipt, archive manifest, handoff summary, quality attestation, completion audit, retention manifest, billing reconciliation, source lineage archive, notification, URL activation, or final artifact is created",
    ],
  })),
  operatorArchiveHandoffPackageResultReconciliationPlanMidnightOil: vi.fn(async () => ({
    receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
    operator_archive_handoff_package_plan_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-plan",
    final_closeout_archive_reconciliation_plan_receipt_id:
      "midnight-oil-test-final-closeout-archive-reconciliation-plan",
    retention_billing_reconciliation_plan_receipt_id:
      "midnight-oil-test-retention-billing-reconciliation-plan",
    delivery_notification_reconciliation_plan_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-plan",
    workspace_delivery_card_reconciliation_plan_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
    operator_delivery_ledger_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_operator_archive_handoff_package_result_reconciliation_unimplemented",
    adapter_key: "operator_archive_handoff_package_result_reconciliation",
    planned_operator_archive_handoff_package_result_reconciliation_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-receipt",
    planned_operator_archive_package_result_entry_id:
      "midnight-oil-test-operator-archive-package-result-entry",
    planned_operator_archive_manifest_status_entry_id:
      "midnight-oil-test-operator-archive-manifest-status-entry",
    planned_operator_handoff_bundle_status_entry_id:
      "midnight-oil-test-operator-handoff-bundle-status-entry",
    planned_operator_archive_handoff_package_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-receipt",
    planned_operator_archive_package_id:
      "midnight-oil-test-operator-archive-package",
    planned_operator_archive_manifest_id:
      "midnight-oil-test-operator-archive-manifest",
    planned_operator_handoff_bundle_id:
      "midnight-oil-test-operator-handoff-bundle",
    planned_final_closeout_archive_reconciliation_receipt_id:
      "midnight-oil-test-final-closeout-archive-reconciliation-receipt",
    planned_artifact_archive_manifest_id:
      "midnight-oil-test-final-artifact-archive-manifest",
    planned_operator_handoff_summary_id:
      "midnight-oil-test-operator-handoff-summary",
    operator_archive_handoff_package_result_reconciliation_blockers: [
      "operator archive handoff package result reconciliation receipt writer",
      "operator archive package result entry writer",
      "operator archive manifest status entry writer",
      "operator handoff bundle status entry writer",
      "operator archive handoff package result reconciliation replay guard",
    ],
    required_operator_archive_handoff_package_result_reconciliation_invariants: [
      "operator archive handoff package result reconciliation planner must require operator archive handoff package planning before package result rows can be reconciled",
    ],
    required_operator_archive_handoff_package_result_reconciliation_receipt_fields: [
      "operator_archive_handoff_package_result_reconciliation_plan_receipt_id",
      "operator_archive_handoff_package_plan_receipt_id",
      "operator_archive_package_result_entry_id",
      "operator_archive_manifest_status_entry_id",
      "operator_handoff_bundle_status_entry_id",
      "operator_archive_package_id",
      "operator_archive_manifest_id",
      "operator_handoff_bundle_id",
    ],
    blocker_reason:
      "operator_archive_handoff_package_result_reconciliation_unimplemented",
    operator_archive_handoff_package_result_reconciliation_allowed: false,
    operator_archive_package_result_entry_created: false,
    operator_archive_manifest_status_entry_created: false,
    operator_handoff_bundle_status_entry_created: false,
    operator_archive_handoff_package_allowed: false,
    operator_archive_package_created: false,
    operator_archive_manifest_created: false,
    operator_handoff_bundle_created: false,
    final_closeout_archive_reconciliation_allowed: false,
    final_run_closure_receipt_reconciled: false,
    run_closeout_record_reconciled: false,
    artifact_archive_manifest_reconciled: false,
    operator_handoff_summary_reconciled: false,
    quality_attestation_reconciled: false,
    completion_audit_entry_reconciled: false,
    retention_billing_reconciliation_allowed: false,
    adapter_plan_notes: [
      "operator archive handoff package result reconciliation plan only: no package result entry, archive manifest status entry, handoff bundle status entry, operator archive package, operator archive manifest, handoff bundle, closeout archive reconciliation receipt, archive manifest, handoff summary, quality attestation, completion audit, retention manifest, billing reconciliation, source lineage archive, notification, URL activation, or final artifact is created",
    ],
  })),
  operatorArchiveHandoffPackageDeliveryAuditPlanMidnightOil: vi.fn(async () => ({
    receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-delivery-audit-plan",
    operator_archive_handoff_package_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
    operator_archive_handoff_package_plan_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-plan",
    final_closeout_archive_reconciliation_plan_receipt_id:
      "midnight-oil-test-final-closeout-archive-reconciliation-plan",
    retention_billing_reconciliation_plan_receipt_id:
      "midnight-oil-test-retention-billing-reconciliation-plan",
    delivery_notification_reconciliation_plan_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-plan",
    workspace_delivery_card_reconciliation_plan_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
    operator_delivery_ledger_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_operator_archive_handoff_package_delivery_audit_unimplemented",
    adapter_key: "operator_archive_handoff_package_delivery_audit",
    planned_operator_archive_handoff_package_delivery_audit_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-delivery-audit-receipt",
    planned_operator_archive_package_delivery_audit_entry_id:
      "midnight-oil-test-operator-archive-package-delivery-audit-entry",
    planned_operator_archive_manifest_delivery_audit_entry_id:
      "midnight-oil-test-operator-archive-manifest-delivery-audit-entry",
    planned_operator_handoff_bundle_delivery_audit_entry_id:
      "midnight-oil-test-operator-handoff-bundle-delivery-audit-entry",
    planned_operator_archive_delivery_audit_evidence_bundle_id:
      "midnight-oil-test-operator-archive-delivery-audit-evidence-bundle",
    planned_operator_archive_handoff_package_result_reconciliation_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-receipt",
    planned_operator_archive_package_result_entry_id:
      "midnight-oil-test-operator-archive-package-result-entry",
    planned_operator_archive_manifest_status_entry_id:
      "midnight-oil-test-operator-archive-manifest-status-entry",
    planned_operator_handoff_bundle_status_entry_id:
      "midnight-oil-test-operator-handoff-bundle-status-entry",
    planned_operator_archive_handoff_package_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-receipt",
    planned_operator_archive_package_id:
      "midnight-oil-test-operator-archive-package",
    planned_operator_archive_manifest_id:
      "midnight-oil-test-operator-archive-manifest",
    planned_operator_handoff_bundle_id:
      "midnight-oil-test-operator-handoff-bundle",
    planned_final_closeout_archive_reconciliation_receipt_id:
      "midnight-oil-test-final-closeout-archive-reconciliation-receipt",
    planned_artifact_archive_manifest_id:
      "midnight-oil-test-final-artifact-archive-manifest",
    planned_operator_handoff_summary_id:
      "midnight-oil-test-operator-handoff-summary",
    operator_archive_handoff_package_delivery_audit_blockers: [
      "operator archive handoff package delivery audit receipt writer",
      "operator archive package delivery audit entry writer",
      "operator archive manifest delivery audit entry writer",
      "operator handoff bundle delivery audit entry writer",
      "operator archive delivery audit evidence bundle writer",
      "operator archive delivery audit replay guard",
    ],
    required_operator_archive_handoff_package_delivery_audit_invariants: [
      "operator archive handoff package delivery audit planner must require package result reconciliation planning before delivery audit rows can be planned",
    ],
    required_operator_archive_handoff_package_delivery_audit_receipt_fields: [
      "operator_archive_handoff_package_delivery_audit_plan_receipt_id",
      "operator_archive_handoff_package_result_reconciliation_plan_receipt_id",
      "operator_archive_handoff_package_delivery_audit_receipt_id",
      "operator_archive_package_delivery_audit_entry_id",
      "operator_archive_manifest_delivery_audit_entry_id",
      "operator_handoff_bundle_delivery_audit_entry_id",
      "operator_archive_delivery_audit_evidence_bundle_id",
    ],
    blocker_reason: "operator_archive_handoff_package_delivery_audit_unimplemented",
    operator_archive_handoff_package_delivery_audit_allowed: false,
    operator_archive_package_delivery_audit_entry_created: false,
    operator_archive_manifest_delivery_audit_entry_created: false,
    operator_handoff_bundle_delivery_audit_entry_created: false,
    operator_archive_delivery_audit_evidence_bundle_created: false,
    operator_archive_handoff_package_result_reconciliation_allowed: false,
    operator_archive_package_result_entry_created: false,
    operator_archive_manifest_status_entry_created: false,
    operator_handoff_bundle_status_entry_created: false,
    operator_archive_handoff_package_allowed: false,
    operator_archive_package_created: false,
    operator_archive_manifest_created: false,
    operator_handoff_bundle_created: false,
    final_closeout_archive_reconciliation_allowed: false,
    final_run_closure_receipt_reconciled: false,
    run_closeout_record_reconciled: false,
    artifact_archive_manifest_reconciled: false,
    operator_handoff_summary_reconciled: false,
    quality_attestation_reconciled: false,
    completion_audit_entry_reconciled: false,
    retention_billing_reconciliation_allowed: false,
    adapter_plan_notes: [
      "operator archive handoff package delivery audit plan only: no package delivery audit entry, archive manifest delivery audit entry, handoff bundle delivery audit entry, evidence bundle, package result entry, archive manifest status entry, handoff bundle status entry, operator archive package, operator archive manifest, handoff bundle, notification, URL activation, or final artifact is created",
    ],
  })),
  operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanMidnightOil: vi.fn(
    async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-plan",
      operator_archive_handoff_package_delivery_audit_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-plan",
      operator_archive_handoff_package_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
      operator_archive_handoff_package_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-plan",
      final_closeout_archive_reconciliation_plan_receipt_id:
        "midnight-oil-test-final-closeout-archive-reconciliation-plan",
      retention_billing_reconciliation_plan_receipt_id:
        "midnight-oil-test-retention-billing-reconciliation-plan",
      delivery_notification_reconciliation_plan_receipt_id:
        "midnight-oil-test-delivery-notification-reconciliation-plan",
      workspace_delivery_card_reconciliation_plan_receipt_id:
        "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
      operator_delivery_ledger_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
      operator_notification_delivery_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
      operator_notification_delivery_apply_plan_receipt_id:
        "midnight-oil-test-operator-notification-delivery-apply-plan",
      operator_notification_delivery_readiness_plan_receipt_id:
        "midnight-oil-test-operator-notification-delivery-readiness-plan",
      final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
      final_artifact_completion_finalization_plan_receipt_id:
        "midnight-oil-test-final-artifact-completion-finalization-plan",
      final_artifact_publish_plan_receipt_id:
        "midnight-oil-test-final-artifact-publish-plan",
      launch_packet_id: "midnight-oil-test-launch-packet",
      approval_receipt_id: "midnight-oil-test-approval-receipt",
      runner_handoff_id: "midnight-oil-test-runner-handoff",
      run_id: "midnight-oil-test",
      status:
        "blocked_operator_archive_handoff_package_delivery_audit_result_reconciliation_unimplemented",
      adapter_key:
        "operator_archive_handoff_package_delivery_audit_result_reconciliation",
      planned_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_audit_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-audit-result-entry",
      planned_operator_archive_manifest_delivery_audit_status_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-audit-status-entry",
      planned_operator_handoff_bundle_delivery_audit_status_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-audit-status-entry",
      planned_operator_archive_delivery_audit_evidence_status_entry_id:
        "midnight-oil-test-operator-archive-delivery-audit-evidence-status-entry",
      planned_operator_archive_handoff_package_delivery_audit_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-receipt",
      planned_operator_archive_package_delivery_audit_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-audit-entry",
      planned_operator_archive_manifest_delivery_audit_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-audit-entry",
      planned_operator_handoff_bundle_delivery_audit_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-audit-entry",
      planned_operator_archive_delivery_audit_evidence_bundle_id:
        "midnight-oil-test-operator-archive-delivery-audit-evidence-bundle",
      planned_operator_archive_handoff_package_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-receipt",
      planned_operator_archive_package_result_entry_id:
        "midnight-oil-test-operator-archive-package-result-entry",
      planned_operator_archive_manifest_status_entry_id:
        "midnight-oil-test-operator-archive-manifest-status-entry",
      planned_operator_handoff_bundle_status_entry_id:
        "midnight-oil-test-operator-handoff-bundle-status-entry",
      planned_operator_archive_handoff_package_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-receipt",
      planned_operator_archive_package_id:
        "midnight-oil-test-operator-archive-package",
      planned_operator_archive_manifest_id:
        "midnight-oil-test-operator-archive-manifest",
      planned_operator_handoff_bundle_id:
        "midnight-oil-test-operator-handoff-bundle",
      planned_final_closeout_archive_reconciliation_receipt_id:
        "midnight-oil-test-final-closeout-archive-reconciliation-receipt",
      planned_artifact_archive_manifest_id:
        "midnight-oil-test-final-artifact-archive-manifest",
      planned_operator_handoff_summary_id:
        "midnight-oil-test-operator-handoff-summary",
      operator_archive_handoff_package_delivery_audit_result_reconciliation_blockers:
        [
          "operator archive handoff package delivery audit result reconciliation receipt writer",
          "operator archive package delivery audit result entry writer",
          "operator archive manifest delivery audit status entry writer",
          "operator handoff bundle delivery audit status entry writer",
          "operator archive delivery audit evidence status entry writer",
          "operator archive delivery audit result reconciliation replay guard",
        ],
      required_operator_archive_handoff_package_delivery_audit_result_reconciliation_invariants:
        [
          "operator archive handoff package delivery audit result reconciliation planner must require delivery audit planning before audit result rows can be reconciled",
        ],
      required_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_fields:
        [
          "operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt_id",
          "operator_archive_handoff_package_delivery_audit_plan_receipt_id",
          "operator_archive_package_delivery_audit_result_entry_id",
          "operator_archive_manifest_delivery_audit_status_entry_id",
          "operator_handoff_bundle_delivery_audit_status_entry_id",
          "operator_archive_delivery_audit_evidence_status_entry_id",
        ],
      blocker_reason:
        "operator_archive_handoff_package_delivery_audit_result_reconciliation_unimplemented",
      operator_archive_handoff_package_delivery_audit_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_audit_result_entry_created: false,
      operator_archive_manifest_delivery_audit_status_entry_created: false,
      operator_handoff_bundle_delivery_audit_status_entry_created: false,
      operator_archive_delivery_audit_evidence_status_entry_created: false,
      operator_archive_handoff_package_delivery_audit_allowed: false,
      operator_archive_package_delivery_audit_entry_created: false,
      operator_archive_manifest_delivery_audit_entry_created: false,
      operator_handoff_bundle_delivery_audit_entry_created: false,
      operator_archive_delivery_audit_evidence_bundle_created: false,
      operator_archive_handoff_package_result_reconciliation_allowed: false,
      operator_archive_package_result_entry_created: false,
      operator_archive_manifest_status_entry_created: false,
      operator_handoff_bundle_status_entry_created: false,
      operator_archive_handoff_package_allowed: false,
      operator_archive_package_created: false,
      operator_archive_manifest_created: false,
      operator_handoff_bundle_created: false,
      final_closeout_archive_reconciliation_allowed: false,
      final_run_closure_receipt_reconciled: false,
      run_closeout_record_reconciled: false,
      artifact_archive_manifest_reconciled: false,
      operator_handoff_summary_reconciled: false,
      quality_attestation_reconciled: false,
      completion_audit_entry_reconciled: false,
      retention_billing_reconciliation_allowed: false,
      adapter_plan_notes: [
        "operator archive handoff package delivery audit result reconciliation plan only: no delivery audit result entry, manifest audit status entry, handoff bundle audit status entry, evidence status entry, package delivery audit entry, archive manifest delivery audit entry, handoff bundle delivery audit entry, evidence bundle, package result entry, archive manifest status entry, handoff bundle status entry, notification, URL activation, or final artifact is created",
      ],
    }),
  ),
  operatorArchivePackageDeliveryReportPlanMidnightOil: vi.fn(async () => ({
    receipt_id: "midnight-oil-test-operator-archive-package-delivery-report-plan",
    operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-plan",
    operator_archive_handoff_package_delivery_audit_plan_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-delivery-audit-plan",
    operator_archive_handoff_package_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
    operator_archive_handoff_package_plan_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-plan",
    final_closeout_archive_reconciliation_plan_receipt_id:
      "midnight-oil-test-final-closeout-archive-reconciliation-plan",
    retention_billing_reconciliation_plan_receipt_id:
      "midnight-oil-test-retention-billing-reconciliation-plan",
    delivery_notification_reconciliation_plan_receipt_id:
      "midnight-oil-test-delivery-notification-reconciliation-plan",
    workspace_delivery_card_reconciliation_plan_receipt_id:
      "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
    operator_delivery_ledger_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
    operator_notification_delivery_result_reconciliation_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
    operator_notification_delivery_apply_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-apply-plan",
    operator_notification_delivery_readiness_plan_receipt_id:
      "midnight-oil-test-operator-notification-delivery-readiness-plan",
    final_run_closure_plan_receipt_id: "midnight-oil-test-final-run-closure-plan",
    final_artifact_completion_finalization_plan_receipt_id:
      "midnight-oil-test-final-artifact-completion-finalization-plan",
    final_artifact_publish_plan_receipt_id:
      "midnight-oil-test-final-artifact-publish-plan",
    launch_packet_id: "midnight-oil-test-launch-packet",
    approval_receipt_id: "midnight-oil-test-approval-receipt",
    runner_handoff_id: "midnight-oil-test-runner-handoff",
    run_id: "midnight-oil-test",
    status: "blocked_operator_archive_package_delivery_report_unimplemented",
    adapter_key: "operator_archive_package_delivery_report",
    planned_operator_archive_package_delivery_report_receipt_id:
      "midnight-oil-test-operator-archive-package-delivery-report-receipt",
    planned_operator_archive_package_delivery_report_entry_id:
      "midnight-oil-test-operator-archive-package-delivery-report-entry",
    planned_operator_archive_manifest_delivery_report_entry_id:
      "midnight-oil-test-operator-archive-manifest-delivery-report-entry",
    planned_operator_handoff_bundle_delivery_report_entry_id:
      "midnight-oil-test-operator-handoff-bundle-delivery-report-entry",
    planned_operator_archive_delivery_report_evidence_bundle_id:
      "midnight-oil-test-operator-archive-delivery-report-evidence-bundle",
    planned_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-receipt",
    planned_operator_archive_package_delivery_audit_result_entry_id:
      "midnight-oil-test-operator-archive-package-delivery-audit-result-entry",
    planned_operator_archive_manifest_delivery_audit_status_entry_id:
      "midnight-oil-test-operator-archive-manifest-delivery-audit-status-entry",
    planned_operator_handoff_bundle_delivery_audit_status_entry_id:
      "midnight-oil-test-operator-handoff-bundle-delivery-audit-status-entry",
    planned_operator_archive_delivery_audit_evidence_status_entry_id:
      "midnight-oil-test-operator-archive-delivery-audit-evidence-status-entry",
    planned_operator_archive_handoff_package_delivery_audit_receipt_id:
      "midnight-oil-test-operator-archive-handoff-package-delivery-audit-receipt",
    planned_operator_archive_package_delivery_audit_entry_id:
      "midnight-oil-test-operator-archive-package-delivery-audit-entry",
    planned_operator_archive_manifest_delivery_audit_entry_id:
      "midnight-oil-test-operator-archive-manifest-delivery-audit-entry",
    planned_operator_handoff_bundle_delivery_audit_entry_id:
      "midnight-oil-test-operator-handoff-bundle-delivery-audit-entry",
    planned_operator_archive_delivery_audit_evidence_bundle_id:
      "midnight-oil-test-operator-archive-delivery-audit-evidence-bundle",
    planned_operator_archive_package_result_entry_id:
      "midnight-oil-test-operator-archive-package-result-entry",
    planned_operator_archive_manifest_status_entry_id:
      "midnight-oil-test-operator-archive-manifest-status-entry",
    planned_operator_handoff_bundle_status_entry_id:
      "midnight-oil-test-operator-handoff-bundle-status-entry",
    planned_operator_archive_package_id:
      "midnight-oil-test-operator-archive-package",
    planned_operator_archive_manifest_id:
      "midnight-oil-test-operator-archive-manifest",
    planned_operator_handoff_bundle_id:
      "midnight-oil-test-operator-handoff-bundle",
    operator_archive_package_delivery_report_blockers: [
      "operator archive package delivery report receipt writer",
      "operator archive package delivery report entry writer",
      "operator archive manifest delivery report entry writer",
      "operator handoff bundle delivery report entry writer",
      "operator archive delivery report evidence bundle writer",
      "operator archive package delivery report replay guard",
    ],
    required_operator_archive_package_delivery_report_invariants: [
      "operator archive package delivery report planner must require delivery audit result reconciliation planning before delivery report rows can be planned",
    ],
    required_operator_archive_package_delivery_report_receipt_fields: [
      "operator_archive_package_delivery_report_plan_receipt_id",
      "operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt_id",
      "operator_archive_package_delivery_report_receipt_id",
      "operator_archive_package_delivery_report_entry_id",
      "operator_archive_manifest_delivery_report_entry_id",
      "operator_handoff_bundle_delivery_report_entry_id",
      "operator_archive_delivery_report_evidence_bundle_id",
    ],
    blocker_reason: "operator_archive_package_delivery_report_unimplemented",
    operator_archive_package_delivery_report_allowed: false,
    operator_archive_package_delivery_report_entry_created: false,
    operator_archive_manifest_delivery_report_entry_created: false,
    operator_handoff_bundle_delivery_report_entry_created: false,
    operator_archive_delivery_report_evidence_bundle_created: false,
    operator_archive_handoff_package_delivery_audit_result_reconciliation_allowed:
      false,
    operator_archive_package_delivery_audit_result_entry_created: false,
    operator_archive_manifest_delivery_audit_status_entry_created: false,
    operator_handoff_bundle_delivery_audit_status_entry_created: false,
    operator_archive_delivery_audit_evidence_status_entry_created: false,
    operator_archive_handoff_package_delivery_audit_allowed: false,
    operator_archive_package_delivery_audit_entry_created: false,
    operator_archive_manifest_delivery_audit_entry_created: false,
    operator_handoff_bundle_delivery_audit_entry_created: false,
    operator_archive_delivery_audit_evidence_bundle_created: false,
    operator_archive_handoff_package_result_reconciliation_allowed: false,
    operator_archive_package_result_entry_created: false,
    operator_archive_manifest_status_entry_created: false,
    operator_handoff_bundle_status_entry_created: false,
    operator_archive_handoff_package_allowed: false,
    operator_archive_package_created: false,
    operator_archive_manifest_created: false,
    operator_handoff_bundle_created: false,
    final_closeout_archive_reconciliation_allowed: false,
    final_run_closure_receipt_reconciled: false,
    run_closeout_record_reconciled: false,
    artifact_archive_manifest_reconciled: false,
    operator_handoff_summary_reconciled: false,
    quality_attestation_reconciled: false,
    completion_audit_entry_reconciled: false,
    retention_billing_reconciliation_allowed: false,
    adapter_plan_notes: [
      "operator archive package delivery report plan only: no package delivery report entry, archive manifest delivery report entry, handoff bundle delivery report entry, evidence bundle, delivery audit result entry, manifest audit status entry, handoff bundle audit status entry, evidence status entry, notification, URL activation, or final artifact is created",
    ],
  })),
  operatorArchivePackageDeliveryReportResultReconciliationPlanMidnightOil: vi.fn(
    async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
      operator_archive_package_delivery_report_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-plan",
      operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-plan",
      operator_archive_handoff_package_delivery_audit_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-plan",
      operator_archive_handoff_package_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
      operator_archive_handoff_package_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-plan",
      final_closeout_archive_reconciliation_plan_receipt_id:
        "midnight-oil-test-final-closeout-archive-reconciliation-plan",
      retention_billing_reconciliation_plan_receipt_id:
        "midnight-oil-test-retention-billing-reconciliation-plan",
      launch_packet_id: "midnight-oil-test-launch-packet",
      approval_receipt_id: "midnight-oil-test-approval-receipt",
      runner_handoff_id: "midnight-oil-test-runner-handoff",
      run_id: "midnight-oil-test",
      status:
        "blocked_operator_archive_package_delivery_report_result_reconciliation_unimplemented",
      adapter_key: "operator_archive_package_delivery_report_result_reconciliation",
      planned_operator_archive_package_delivery_report_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-entry",
      planned_operator_archive_manifest_delivery_report_status_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-report-status-entry",
      planned_operator_handoff_bundle_delivery_report_status_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-report-status-entry",
      planned_operator_archive_delivery_report_evidence_status_entry_id:
        "midnight-oil-test-operator-archive-delivery-report-evidence-status-entry",
      planned_operator_archive_package_delivery_report_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-receipt",
      planned_operator_archive_package_delivery_report_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-entry",
      planned_operator_archive_manifest_delivery_report_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-report-entry",
      planned_operator_handoff_bundle_delivery_report_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-report-entry",
      planned_operator_archive_delivery_report_evidence_bundle_id:
        "midnight-oil-test-operator-archive-delivery-report-evidence-bundle",
      planned_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_audit_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-audit-result-entry",
      planned_operator_archive_manifest_delivery_audit_status_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-audit-status-entry",
      planned_operator_handoff_bundle_delivery_audit_status_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-audit-status-entry",
      planned_operator_archive_delivery_audit_evidence_status_entry_id:
        "midnight-oil-test-operator-archive-delivery-audit-evidence-status-entry",
      planned_operator_archive_handoff_package_delivery_audit_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-receipt",
      planned_operator_archive_package_delivery_audit_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-audit-entry",
      planned_operator_archive_manifest_delivery_audit_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-audit-entry",
      planned_operator_handoff_bundle_delivery_audit_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-audit-entry",
      planned_operator_archive_delivery_audit_evidence_bundle_id:
        "midnight-oil-test-operator-archive-delivery-audit-evidence-bundle",
      operator_archive_package_delivery_report_result_reconciliation_blockers: [
        "operator archive package delivery report result reconciliation receipt writer",
        "operator archive package delivery report result entry writer",
        "operator archive manifest delivery report status entry writer",
        "operator handoff bundle delivery report status entry writer",
        "operator archive delivery report evidence status entry writer",
        "operator archive package delivery report result reconciliation replay guard",
      ],
      required_operator_archive_package_delivery_report_result_reconciliation_invariants:
        [
          "operator archive package delivery report result reconciliation planner must require delivery report planning before report result rows can be reconciled",
        ],
      required_operator_archive_package_delivery_report_result_reconciliation_receipt_fields:
        [
          "operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id",
          "operator_archive_package_delivery_report_plan_receipt_id",
          "operator_archive_package_delivery_report_result_entry_id",
          "operator_archive_manifest_delivery_report_status_entry_id",
          "operator_handoff_bundle_delivery_report_status_entry_id",
          "operator_archive_delivery_report_evidence_status_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_result_reconciliation_unimplemented",
      operator_archive_package_delivery_report_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_result_entry_created: false,
      operator_archive_manifest_delivery_report_status_entry_created: false,
      operator_handoff_bundle_delivery_report_status_entry_created: false,
      operator_archive_delivery_report_evidence_status_entry_created: false,
      operator_archive_package_delivery_report_allowed: false,
      operator_archive_package_delivery_report_entry_created: false,
      operator_archive_manifest_delivery_report_entry_created: false,
      operator_handoff_bundle_delivery_report_entry_created: false,
      operator_archive_delivery_report_evidence_bundle_created: false,
      operator_archive_package_delivery_audit_result_entry_created: false,
      operator_archive_package_delivery_audit_entry_created: false,
      operator_archive_package_result_entry_created: false,
      operator_archive_package_created: false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report result reconciliation plan only: no report result entry, manifest report status entry, handoff bundle report status entry, evidence status entry, package delivery report entry, archive manifest delivery report entry, handoff bundle delivery report entry, report evidence bundle, notification, URL activation, or final artifact is created",
      ],
    }),
  ),
  operatorArchivePackageDeliveryReportNotificationReadinessPlanMidnightOil: vi.fn(
    async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-plan",
      operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
      operator_archive_package_delivery_report_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-plan",
      operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-plan",
      operator_archive_handoff_package_delivery_audit_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-plan",
      operator_archive_handoff_package_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
      operator_archive_handoff_package_plan_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-plan",
      final_closeout_archive_reconciliation_plan_receipt_id:
        "midnight-oil-test-final-closeout-archive-reconciliation-plan",
      retention_billing_reconciliation_plan_receipt_id:
        "midnight-oil-test-retention-billing-reconciliation-plan",
      launch_packet_id: "midnight-oil-test-launch-packet",
      approval_receipt_id: "midnight-oil-test-approval-receipt",
      runner_handoff_id: "midnight-oil-test-runner-handoff",
      run_id: "midnight-oil-test",
      status:
        "blocked_operator_archive_package_delivery_report_notification_readiness_unimplemented",
      adapter_key: "operator_archive_package_delivery_report_notification_readiness",
      planned_operator_archive_package_delivery_report_notification_readiness_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-receipt",
      planned_operator_archive_package_delivery_report_notification_payload_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-payload",
      planned_operator_archive_package_delivery_report_notification_channel_policy_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-channel-policy",
      planned_operator_archive_package_delivery_report_notification_audit_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-audit",
      planned_operator_archive_package_delivery_report_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-entry",
      planned_operator_archive_manifest_delivery_report_status_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-report-status-entry",
      planned_operator_handoff_bundle_delivery_report_status_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-report-status-entry",
      planned_operator_archive_delivery_report_evidence_status_entry_id:
        "midnight-oil-test-operator-archive-delivery-report-evidence-status-entry",
      planned_operator_archive_package_delivery_report_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-receipt",
      planned_operator_archive_package_delivery_report_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-entry",
      planned_operator_archive_manifest_delivery_report_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-report-entry",
      planned_operator_handoff_bundle_delivery_report_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-report-entry",
      planned_operator_archive_delivery_report_evidence_bundle_id:
        "midnight-oil-test-operator-archive-delivery-report-evidence-bundle",
      planned_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_audit_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-audit-result-entry",
      planned_operator_archive_manifest_delivery_audit_status_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-audit-status-entry",
      planned_operator_handoff_bundle_delivery_audit_status_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-audit-status-entry",
      planned_operator_archive_delivery_audit_evidence_status_entry_id:
        "midnight-oil-test-operator-archive-delivery-audit-evidence-status-entry",
      planned_operator_archive_handoff_package_delivery_audit_receipt_id:
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-receipt",
      planned_operator_archive_package_delivery_audit_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-audit-entry",
      planned_operator_archive_manifest_delivery_audit_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-audit-entry",
      planned_operator_handoff_bundle_delivery_audit_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-audit-entry",
      planned_operator_archive_delivery_audit_evidence_bundle_id:
        "midnight-oil-test-operator-archive-delivery-audit-evidence-bundle",
      operator_archive_package_delivery_report_notification_readiness_blockers: [
        "operator archive package delivery report notification readiness receipt writer",
        "operator archive package delivery report notification payload writer",
        "operator archive package delivery report notification channel policy writer",
        "operator archive package delivery report notification audit writer",
        "operator archive package delivery report notification readiness replay guard",
      ],
      required_operator_archive_package_delivery_report_notification_readiness_invariants:
        [
          "operator archive package delivery report notification readiness planner must require report result reconciliation planning before notification payloads can be planned",
        ],
      required_operator_archive_package_delivery_report_notification_readiness_receipt_fields:
        [
          "operator_archive_package_delivery_report_notification_readiness_receipt_id",
          "operator_archive_package_delivery_report_notification_payload_id",
          "operator_archive_package_delivery_report_notification_channel_policy_id",
          "operator_archive_package_delivery_report_notification_audit_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_notification_readiness_unimplemented",
      operator_archive_package_delivery_report_notification_readiness_allowed:
        false,
      operator_archive_package_delivery_report_notification_payload_created: false,
      operator_archive_package_delivery_report_notification_channel_policy_created:
        false,
      operator_archive_package_delivery_report_notification_audit_created: false,
      operator_archive_package_delivery_report_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_result_entry_created: false,
      operator_archive_manifest_delivery_report_status_entry_created: false,
      operator_handoff_bundle_delivery_report_status_entry_created: false,
      operator_archive_delivery_report_evidence_status_entry_created: false,
      operator_archive_package_delivery_report_allowed: false,
      operator_archive_package_delivery_report_entry_created: false,
      operator_archive_manifest_delivery_report_entry_created: false,
      operator_handoff_bundle_delivery_report_entry_created: false,
      operator_archive_delivery_report_evidence_bundle_created: false,
      operator_archive_package_delivery_audit_result_entry_created: false,
      operator_archive_package_delivery_audit_entry_created: false,
      operator_archive_package_result_entry_created: false,
      operator_archive_package_created: false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report notification readiness plan only: no notification readiness receipt, payload, channel policy, audit, notification dispatch, URL activation, or final artifact is created",
      ],
    }),
  ),
  operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanMidnightOil:
    vi.fn(async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-plan",
      operator_archive_package_delivery_report_notification_readiness_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-plan",
      operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
      operator_archive_package_delivery_report_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-plan",
      status:
        "blocked_operator_archive_package_delivery_report_notification_result_reconciliation_unimplemented",
      adapter_key:
        "operator_archive_package_delivery_report_notification_result_reconciliation",
      planned_operator_archive_package_delivery_report_notification_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_notification_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-entry",
      planned_operator_archive_package_delivery_report_notification_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-status-entry",
      planned_operator_archive_package_delivery_report_notification_audit_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-audit-status-entry",
      planned_operator_archive_package_delivery_report_notification_readiness_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-receipt",
      planned_operator_archive_package_delivery_report_notification_payload_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-payload",
      planned_operator_archive_package_delivery_report_notification_channel_policy_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-channel-policy",
      planned_operator_archive_package_delivery_report_notification_audit_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-audit",
      planned_operator_archive_package_delivery_report_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-entry",
      planned_operator_archive_manifest_delivery_report_status_entry_id:
        "midnight-oil-test-operator-archive-manifest-delivery-report-status-entry",
      planned_operator_handoff_bundle_delivery_report_status_entry_id:
        "midnight-oil-test-operator-handoff-bundle-delivery-report-status-entry",
      planned_operator_archive_delivery_report_evidence_status_entry_id:
        "midnight-oil-test-operator-archive-delivery-report-evidence-status-entry",
      planned_operator_archive_package_delivery_report_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-receipt",
      planned_operator_archive_package_delivery_report_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-entry",
      operator_archive_package_delivery_report_notification_result_reconciliation_blockers:
        [
          "operator archive package delivery report notification result reconciliation receipt writer",
          "operator archive package delivery report notification result entry writer",
          "operator archive package delivery report notification status entry writer",
          "operator archive package delivery report notification audit status entry writer",
          "operator archive package delivery report notification result reconciliation replay guard",
        ],
      required_operator_archive_package_delivery_report_notification_result_reconciliation_invariants:
        [
          "operator archive package delivery report notification result reconciliation planner must require notification readiness planning before notification result rows can be reconciled",
        ],
      required_operator_archive_package_delivery_report_notification_result_reconciliation_receipt_fields:
        [
          "operator_archive_package_delivery_report_notification_result_reconciliation_receipt_id",
          "operator_archive_package_delivery_report_notification_result_entry_id",
          "operator_archive_package_delivery_report_notification_status_entry_id",
          "operator_archive_package_delivery_report_notification_audit_status_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_notification_result_reconciliation_unimplemented",
      operator_archive_package_delivery_report_notification_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_notification_result_entry_created:
        false,
      operator_archive_package_delivery_report_notification_status_entry_created:
        false,
      operator_archive_package_delivery_report_notification_audit_status_entry_created:
        false,
      operator_archive_package_delivery_report_notification_readiness_allowed:
        false,
      operator_archive_package_delivery_report_notification_payload_created: false,
      operator_archive_package_delivery_report_notification_channel_policy_created:
        false,
      operator_archive_package_delivery_report_notification_audit_created: false,
      operator_archive_package_delivery_report_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_result_entry_created: false,
      operator_archive_manifest_delivery_report_status_entry_created: false,
      operator_handoff_bundle_delivery_report_status_entry_created: false,
      operator_archive_delivery_report_evidence_status_entry_created: false,
      operator_archive_package_delivery_report_allowed: false,
      operator_archive_package_delivery_report_entry_created: false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report notification result reconciliation plan only: no notification result entry, status entry, audit status entry, dispatch, URL activation, or final artifact is created",
      ],
    })),
  operatorArchivePackageDeliveryReportDeliveryConfirmationPlanMidnightOil: vi.fn(
    async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-plan",
      operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-plan",
      operator_archive_package_delivery_report_notification_readiness_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-plan",
      operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
      operator_archive_package_delivery_report_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-plan",
      status:
        "blocked_operator_archive_package_delivery_report_delivery_confirmation_unimplemented",
      adapter_key: "operator_archive_package_delivery_report_delivery_confirmation",
      planned_operator_archive_package_delivery_report_delivery_confirmation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-receipt",
      planned_operator_archive_package_delivery_report_delivery_confirmation_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-status-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_audit_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-audit-entry",
      planned_operator_archive_package_delivery_report_notification_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_notification_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-entry",
      planned_operator_archive_package_delivery_report_notification_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-status-entry",
      planned_operator_archive_package_delivery_report_notification_audit_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-audit-status-entry",
      operator_archive_package_delivery_report_delivery_confirmation_blockers: [
        "operator archive package delivery report delivery confirmation receipt writer",
        "operator archive package delivery report delivery confirmation entry writer",
        "operator archive package delivery report delivery confirmation status entry writer",
        "operator archive package delivery report delivery confirmation audit entry writer",
        "operator archive package delivery report delivery confirmation replay guard",
      ],
      required_operator_archive_package_delivery_report_delivery_confirmation_invariants:
        [
          "operator archive package delivery report delivery confirmation planner must require notification result reconciliation planning before delivery confirmation rows can be planned",
        ],
      required_operator_archive_package_delivery_report_delivery_confirmation_receipt_fields:
        [
          "operator_archive_package_delivery_report_delivery_confirmation_receipt_id",
          "operator_archive_package_delivery_report_delivery_confirmation_entry_id",
          "operator_archive_package_delivery_report_delivery_confirmation_status_entry_id",
          "operator_archive_package_delivery_report_delivery_confirmation_audit_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_delivery_confirmation_unimplemented",
      operator_archive_package_delivery_report_delivery_confirmation_allowed:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_status_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_audit_entry_created:
        false,
      operator_archive_package_delivery_report_notification_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_notification_result_entry_created:
        false,
      operator_archive_package_delivery_report_notification_status_entry_created:
        false,
      operator_archive_package_delivery_report_notification_audit_status_entry_created:
        false,
      operator_archive_package_delivery_report_notification_readiness_allowed:
        false,
      operator_archive_package_delivery_report_notification_payload_created: false,
      operator_archive_package_delivery_report_notification_channel_policy_created:
        false,
      operator_archive_package_delivery_report_notification_audit_created: false,
      operator_archive_package_delivery_report_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_result_entry_created: false,
      operator_archive_manifest_delivery_report_status_entry_created: false,
      operator_handoff_bundle_delivery_report_status_entry_created: false,
      operator_archive_delivery_report_evidence_status_entry_created: false,
      operator_archive_package_delivery_report_allowed: false,
      operator_archive_package_delivery_report_entry_created: false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report delivery confirmation plan only: no confirmation receipt, entry, status entry, audit entry, dispatch, URL activation, or final artifact is created",
      ],
    }),
  ),
  operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanMidnightOil:
    vi.fn(async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
      operator_archive_package_delivery_report_delivery_confirmation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-plan",
      operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-plan",
      operator_archive_package_delivery_report_notification_readiness_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-plan",
      operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
      operator_archive_package_delivery_report_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-plan",
      status:
        "blocked_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_unimplemented",
      adapter_key:
        "operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation",
      planned_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_delivery_confirmation_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-status-result-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-audit-result-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-receipt",
      planned_operator_archive_package_delivery_report_delivery_confirmation_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-status-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_audit_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-audit-entry",
      operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_blockers:
        [
          "operator archive package delivery report delivery confirmation result reconciliation receipt writer",
          "operator archive package delivery report delivery confirmation result entry writer",
          "operator archive package delivery report delivery confirmation status result entry writer",
          "operator archive package delivery report delivery confirmation audit result entry writer",
          "operator archive package delivery report delivery confirmation result reconciliation replay guard",
        ],
      required_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_invariants:
        [
          "operator archive package delivery report delivery confirmation result reconciliation planner must require delivery confirmation planning before confirmation result rows can be reconciled",
        ],
      required_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_receipt_fields:
        [
          "operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_receipt_id",
          "operator_archive_package_delivery_report_delivery_confirmation_result_entry_id",
          "operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_id",
          "operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_unimplemented",
      operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_result_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_allowed:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_status_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_audit_entry_created:
        false,
      operator_archive_package_delivery_report_notification_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_notification_result_entry_created:
        false,
      operator_archive_package_delivery_report_notification_status_entry_created:
        false,
      operator_archive_package_delivery_report_notification_audit_status_entry_created:
        false,
      operator_archive_package_delivery_report_notification_readiness_allowed:
        false,
      operator_archive_package_delivery_report_notification_payload_created: false,
      operator_archive_package_delivery_report_notification_channel_policy_created:
        false,
      operator_archive_package_delivery_report_notification_audit_created: false,
      operator_archive_package_delivery_report_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_result_entry_created: false,
      operator_archive_manifest_delivery_report_status_entry_created: false,
      operator_handoff_bundle_delivery_report_status_entry_created: false,
      operator_archive_delivery_report_evidence_status_entry_created: false,
      operator_archive_package_delivery_report_allowed: false,
      operator_archive_package_delivery_report_entry_created: false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report delivery confirmation result reconciliation plan only: no confirmation result receipt, entry, status result entry, audit result entry, dispatch, URL activation, or final artifact is created",
      ],
    })),
  operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanMidnightOil:
    vi.fn(async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-plan",
      operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
      operator_archive_package_delivery_report_delivery_confirmation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-plan",
      operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-plan",
      operator_archive_package_delivery_report_notification_readiness_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-plan",
      operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
      operator_archive_package_delivery_report_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-plan",
      status:
        "blocked_operator_archive_package_delivery_report_final_operator_acknowledgement_unimplemented",
      adapter_key:
        "operator_archive_package_delivery_report_final_operator_acknowledgement",
      planned_operator_archive_package_delivery_report_final_operator_acknowledgement_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-receipt",
      planned_operator_archive_package_delivery_report_final_operator_acknowledgement_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-entry",
      planned_operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-status-entry",
      planned_operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-audit-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_delivery_confirmation_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-status-result-entry",
      planned_operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-audit-result-entry",
      operator_archive_package_delivery_report_final_operator_acknowledgement_blockers:
        [
          "operator archive package delivery report final operator acknowledgement receipt writer",
          "operator archive package delivery report final operator acknowledgement entry writer",
          "operator archive package delivery report final operator acknowledgement status entry writer",
          "operator archive package delivery report final operator acknowledgement audit entry writer",
          "operator archive package delivery report final operator acknowledgement replay guard",
        ],
      required_operator_archive_package_delivery_report_final_operator_acknowledgement_invariants:
        [
          "operator archive package delivery report final operator acknowledgement planner must require delivery confirmation result reconciliation before acknowledgement rows can be planned",
        ],
      required_operator_archive_package_delivery_report_final_operator_acknowledgement_receipt_fields:
        [
          "operator_archive_package_delivery_report_final_operator_acknowledgement_receipt_id",
          "operator_archive_package_delivery_report_final_operator_acknowledgement_entry_id",
          "operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_id",
          "operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_final_operator_acknowledgement_unimplemented",
      operator_archive_package_delivery_report_final_operator_acknowledgement_allowed:
        false,
      operator_archive_package_delivery_report_final_operator_acknowledgement_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_result_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_allowed:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_status_entry_created:
        false,
      operator_archive_package_delivery_report_delivery_confirmation_audit_entry_created:
        false,
      operator_archive_package_delivery_report_notification_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_notification_result_entry_created:
        false,
      operator_archive_package_delivery_report_notification_status_entry_created:
        false,
      operator_archive_package_delivery_report_notification_audit_status_entry_created:
        false,
      operator_archive_package_delivery_report_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_result_entry_created: false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report final operator acknowledgement plan only: no acknowledgement receipt, entry, status entry, audit entry, dispatch, URL activation, or final artifact is created",
      ],
    })),
  operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanMidnightOil:
    vi.fn(async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan",
      operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-plan",
      operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
      status:
        "blocked_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_unimplemented",
      adapter_key:
        "operator_archive_package_delivery_report_acknowledgement_result_reconciliation",
      planned_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_acknowledgement_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-entry",
      planned_operator_archive_package_delivery_report_acknowledgement_status_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-status-result-entry",
      planned_operator_archive_package_delivery_report_acknowledgement_audit_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-audit-result-entry",
      operator_archive_package_delivery_report_acknowledgement_result_reconciliation_blockers:
        [
          "operator archive package delivery report acknowledgement result reconciliation receipt writer",
          "operator archive package delivery report acknowledgement result entry writer",
          "operator archive package delivery report acknowledgement status result entry writer",
          "operator archive package delivery report acknowledgement audit result entry writer",
        ],
      required_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_invariants:
        [
          "operator archive package delivery report acknowledgement result reconciliation planner must require final operator acknowledgement before acknowledgement result rows can be planned",
        ],
      required_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_receipt_fields:
        [
          "operator_archive_package_delivery_report_acknowledgement_result_reconciliation_receipt_id",
          "operator_archive_package_delivery_report_acknowledgement_result_entry_id",
          "operator_archive_package_delivery_report_acknowledgement_status_result_entry_id",
          "operator_archive_package_delivery_report_acknowledgement_audit_result_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_acknowledgement_result_reconciliation_unimplemented",
      operator_archive_package_delivery_report_acknowledgement_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_acknowledgement_result_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_status_result_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_audit_result_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_acknowledgement_allowed:
        false,
      operator_archive_package_delivery_report_final_operator_acknowledgement_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_created:
        false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report acknowledgement result reconciliation plan only: no acknowledgement result receipt, entry, status result entry, audit result entry, dispatch, URL activation, or final artifact is created",
      ],
    })),
  operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanMidnightOil:
    vi.fn(async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-plan",
      operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan",
      operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-plan",
      operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
      status:
        "blocked_operator_archive_package_delivery_report_final_closeout_acknowledgement_unimplemented",
      adapter_key:
        "operator_archive_package_delivery_report_final_closeout_acknowledgement",
      planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-receipt",
      planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-entry",
      planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-status-entry",
      planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-audit-entry",
      operator_archive_package_delivery_report_final_closeout_acknowledgement_blockers:
        [
          "operator archive package delivery report final closeout acknowledgement receipt writer",
          "operator archive package delivery report final closeout acknowledgement entry writer",
          "operator archive package delivery report final closeout acknowledgement status entry writer",
          "operator archive package delivery report final closeout acknowledgement audit entry writer",
        ],
      required_operator_archive_package_delivery_report_final_closeout_acknowledgement_invariants:
        [
          "operator archive package delivery report final closeout acknowledgement planner must require acknowledgement result reconciliation before final closeout acknowledgement rows can be planned",
        ],
      required_operator_archive_package_delivery_report_final_closeout_acknowledgement_receipt_fields:
        [
          "operator_archive_package_delivery_report_final_closeout_acknowledgement_receipt_id",
          "operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_id",
          "operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_id",
          "operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_final_closeout_acknowledgement_unimplemented",
      operator_archive_package_delivery_report_final_closeout_acknowledgement_allowed:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_created:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_created:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_acknowledgement_result_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_status_result_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_audit_result_entry_created:
        false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report final closeout acknowledgement plan only: no final closeout acknowledgement receipt, entry, status entry, audit entry, dispatch, URL activation, or final artifact is created",
      ],
    })),
  operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanMidnightOil:
    vi.fn(async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-plan",
      operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-plan",
      operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan",
      operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-plan",
      operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
      status:
        "blocked_operator_archive_package_delivery_report_final_operator_delivery_closeout_unimplemented",
      adapter_key:
        "operator_archive_package_delivery_report_final_operator_delivery_closeout",
      planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-receipt",
      planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-entry",
      planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-status-entry",
      planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-audit-entry",
      operator_archive_package_delivery_report_final_operator_delivery_closeout_blockers:
        [
          "operator archive package delivery report final operator delivery closeout receipt writer",
          "operator archive package delivery report final operator delivery closeout entry writer",
          "operator archive package delivery report final operator delivery closeout status entry writer",
          "operator archive package delivery report final operator delivery closeout audit entry writer",
        ],
      required_operator_archive_package_delivery_report_final_operator_delivery_closeout_invariants:
        [
          "operator archive package delivery report final operator delivery closeout planner must require final closeout acknowledgement before final operator delivery closeout rows can be planned",
        ],
      required_operator_archive_package_delivery_report_final_operator_delivery_closeout_receipt_fields:
        [
          "operator_archive_package_delivery_report_final_operator_delivery_closeout_receipt_id",
          "operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_id",
          "operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_id",
          "operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_final_operator_delivery_closeout_unimplemented",
      operator_archive_package_delivery_report_final_operator_delivery_closeout_allowed:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_created:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_allowed:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_created:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_created:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_acknowledgement_result_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_status_result_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_audit_result_entry_created:
        false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report final operator delivery closeout plan only: no final operator delivery closeout receipt, entry, status entry, audit entry, dispatch, URL activation, or final artifact is created",
      ],
    })),
  operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanMidnightOil:
    vi.fn(async () => ({
      receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-result-reconciliation-plan",
      operator_archive_package_delivery_report_final_operator_delivery_closeout_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-plan",
      operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-plan",
      operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan",
      operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-plan",
      operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
      status:
        "blocked_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_unimplemented",
      adapter_key:
        "operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation",
      planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_receipt_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-result-reconciliation-receipt",
      planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-result-entry",
      planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_status_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-status-result-entry",
      planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_result_entry_id:
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-audit-result-entry",
      operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_blockers:
        [
          "operator archive package delivery report final operator delivery closeout result reconciliation receipt writer",
          "operator archive package delivery report final operator delivery closeout result entry writer",
          "operator archive package delivery report final operator delivery closeout status result entry writer",
          "operator archive package delivery report final operator delivery closeout audit result entry writer",
        ],
      required_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_invariants:
        [
          "operator archive package delivery report final operator delivery closeout result reconciliation planner must require final operator delivery closeout planning before final operator delivery closeout result rows can be planned",
        ],
      required_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_receipt_fields:
        [
          "operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_receipt_id",
          "operator_archive_package_delivery_report_final_operator_delivery_closeout_result_entry_id",
          "operator_archive_package_delivery_report_final_operator_delivery_closeout_status_result_entry_id",
          "operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_result_entry_id",
        ],
      blocker_reason:
        "operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_unimplemented",
      operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_result_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_status_result_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_result_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_allowed:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_created:
        false,
      operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_created:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_allowed:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_created:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_created:
        false,
      operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_result_reconciliation_allowed:
        false,
      operator_archive_package_delivery_report_acknowledgement_result_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_status_result_entry_created:
        false,
      operator_archive_package_delivery_report_acknowledgement_audit_result_entry_created:
        false,
      operator_notification_created: false,
      private_read_url_created: false,
      graph_mutated: false,
      provider_calls_made: false,
      retrieval_performed: false,
      final_artifact_created: false,
      adapter_plan_notes: [
        "operator archive package delivery report final operator delivery closeout result reconciliation plan only: no final operator delivery closeout result receipt, entry, status result entry, audit result entry, dispatch, URL activation, or final artifact is created",
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

    await user.click(screen.getByRole("button", { name: "Repository commit rollback plan" }));

    await waitFor(() => expect(repositoryCommitRollbackPlanMidnightOil).toHaveBeenCalled());
    expect(repositoryCommitRollbackPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
    });
    expect(screen.getByText("Repository commit rollback receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-repository-commit-rollback-plan")).toBeTruthy();
    expect(screen.getByText("blocked repository commit rollback unimplemented")).toBeTruthy();
    expect(screen.getAllByText("midnight-oil-test-repository-transaction").length).toBeGreaterThan(0);
    expect(screen.getAllByText("worker queue claim commit").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-repository-transaction-write-set").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("midnight-oil-test-repository-transaction-lock").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-repository-transaction-commit-receipt").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-repository-transaction-rollback-receipt").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("midnight-oil-test-repository-commit-ledger-entry")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-repository-rollback-ledger-entry")).toBeTruthy();
    expect(
      screen.getByText(
        "repository commit rollback planner must require repository transaction planning before any commit or rollback receipt can be created",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Commit rollback blockers:/)).toBeTruthy();
    expect(screen.getByText(/Commit rollback receipt fields:/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Worker lease heartbeat plan" }));

    await waitFor(() => expect(workerDispatchLeaseHeartbeatPlanMidnightOil).toHaveBeenCalled());
    expect(workerDispatchLeaseHeartbeatPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
    });
    expect(screen.getByText("Worker lease heartbeat receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-dispatch-lease-heartbeat-plan")).toBeTruthy();
    expect(screen.getByText("blocked worker dispatch lease heartbeat unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-lease-heartbeat-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-lease-renewal-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-lease-expiry-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-lease-heartbeat-ledger-entry")).toBeTruthy();
    expect(
      screen.getAllByText("midnight-oil-test-worker-queue-claim-lease-token").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("midnight-oil-test-runner-dispatch-queue").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-runner-dispatch-worker").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-runner-dispatch-worker-lease").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-midnight-oil-runner-dispatch").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("900s").length).toBeGreaterThan(0);
    expect(screen.getAllByText("300s").length).toBeGreaterThan(0);
    expect(screen.getAllByText("60s").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "worker dispatch lease heartbeat planner must require repository commit rollback planning before any worker heartbeat can be recorded",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Worker lease heartbeat blockers:/)).toBeTruthy();
    expect(screen.getByText(/worker lease heartbeat writer/)).toBeTruthy();
    expect(screen.getByText(/worker lease renewal compare-and-swap/)).toBeTruthy();
    expect(screen.getByText(/heartbeat ledger append transaction/)).toBeTruthy();
    expect(screen.getByText(/Worker lease heartbeat receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/heartbeat_ledger_entry_id/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Worker cancellation abandon plan" }));

    await waitFor(() => expect(workerCancellationAbandonPlanMidnightOil).toHaveBeenCalled());
    expect(workerCancellationAbandonPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
    });
    expect(screen.getByText("Worker cancellation abandon receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-cancellation-abandon-plan")).toBeTruthy();
    expect(screen.getByText("blocked worker cancellation abandon unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-cancellation-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-abandon-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-cancellation-ledger-entry")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-abandon-ledger-entry")).toBeTruthy();
    expect(
      screen.getAllByText("midnight-oil-test-worker-queue-claim-lease-token").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-runner-dispatch-worker-lease").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("900s").length).toBeGreaterThan(0);
    expect(screen.getAllByText("300s").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "worker cancellation abandon planner must require worker dispatch lease heartbeat planning before any worker can be cancelled or abandoned",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Worker cancellation abandon blockers:/)).toBeTruthy();
    expect(screen.getByText(/worker cancellation signal writer/)).toBeTruthy();
    expect(screen.getByText(/worker abandon compare-and-swap/)).toBeTruthy();
    expect(screen.getByText(/cancellation ledger append transaction/)).toBeTruthy();
    expect(screen.getByText(/Worker cancellation abandon receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/cancellation_ledger_entry_id/)).toBeTruthy();
    expect(screen.getByText(/worker_abandoned/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Worker completion finalization plan" }));

    await waitFor(() => expect(workerCompletionFinalizationPlanMidnightOil).toHaveBeenCalled());
    expect(workerCompletionFinalizationPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
      worker_cancellation_abandon_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
      }),
    });
    expect(screen.getByText("Worker completion finalization receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-completion-finalization-plan")).toBeTruthy();
    expect(screen.getByText("blocked worker completion finalization unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-completion-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-finalization-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-result-manifest")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-output-bundle")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-completion-ledger-entry")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-finalization-ledger-entry")).toBeTruthy();
    expect(
      screen.getByText(
        "worker completion finalization planner must require worker cancellation abandon planning before any worker completion can be finalized",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Worker completion finalization blockers:/)).toBeTruthy();
    expect(screen.getByText(/worker completion receipt writer/)).toBeTruthy();
    expect(screen.getByText(/worker result manifest durable writer/)).toBeTruthy();
    expect(screen.getByText(/worker finalization ledger append transaction/)).toBeTruthy();
    expect(screen.getByText(/Worker completion finalization receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/worker_result_manifest_id/)).toBeTruthy();
    expect(screen.getByText(/worker_output_bundle_id/)).toBeTruthy();
    expect(screen.getByText(/worker_finalized/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Worker output aggregation plan" }));

    await waitFor(() => expect(workerOutputAggregationPlanMidnightOil).toHaveBeenCalled());
    expect(workerOutputAggregationPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
      worker_cancellation_abandon_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
      }),
      worker_completion_finalization_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-completion-finalization-plan",
      }),
    });
    expect(screen.getByText("Worker output aggregation receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-output-aggregation-plan")).toBeTruthy();
    expect(screen.getByText("blocked worker output aggregation unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-output-aggregation-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-output-index")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-output-manifest")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-output-summary")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-worker-output-aggregation-ledger-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "worker output aggregation planner must require worker completion finalization planning before any worker output can be aggregated",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Worker output aggregation blockers:/)).toBeTruthy();
    expect(screen.getByText(/worker output aggregation receipt writer/)).toBeTruthy();
    expect(screen.getByText(/worker output index durable writer/)).toBeTruthy();
    expect(screen.getByText(/worker output summary synthesis boundary/)).toBeTruthy();
    expect(screen.getByText(/Worker output aggregation receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/worker_output_index_id/)).toBeTruthy();
    expect(screen.getByText(/worker_output_manifest_id/)).toBeTruthy();
    expect(screen.getByText(/worker_output_summary_id/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Worker synthesis handoff plan" }));

    await waitFor(() => expect(workerSynthesisHandoffPlanMidnightOil).toHaveBeenCalled());
    expect(workerSynthesisHandoffPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
      worker_cancellation_abandon_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
      }),
      worker_completion_finalization_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-completion-finalization-plan",
      }),
      worker_output_aggregation_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-output-aggregation-plan",
      }),
    });
    expect(screen.getByText("Worker synthesis handoff receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-synthesis-handoff-plan")).toBeTruthy();
    expect(screen.getByText("blocked worker synthesis handoff unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-synthesis-handoff-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-synthesis-input-bundle")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-synthesis-context-manifest")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-worker-synthesis-outline")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-worker-synthesis-handoff-ledger-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "worker synthesis handoff planner must require worker output aggregation planning before synthesis input can be handed off",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Worker synthesis handoff blockers:/)).toBeTruthy();
    expect(screen.getByText(/worker synthesis handoff receipt writer/)).toBeTruthy();
    expect(screen.getByText(/worker synthesis input bundle durable writer/)).toBeTruthy();
    expect(screen.getByText(/worker synthesis context manifest builder/)).toBeTruthy();
    expect(screen.getByText(/Worker synthesis handoff receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/synthesis_input_bundle_id/)).toBeTruthy();
    expect(screen.getByText(/synthesis_context_manifest_id/)).toBeTruthy();
    expect(screen.getByText(/synthesis_outline_id/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Synthesis bundle assembly plan" }));

    await waitFor(() => expect(synthesisBundleAssemblyPlanMidnightOil).toHaveBeenCalled());
    expect(synthesisBundleAssemblyPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
      worker_cancellation_abandon_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
      }),
      worker_completion_finalization_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-completion-finalization-plan",
      }),
      worker_output_aggregation_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-output-aggregation-plan",
      }),
      worker_synthesis_handoff_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-synthesis-handoff-plan",
      }),
    });
    expect(screen.getByText("Synthesis bundle assembly receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-synthesis-bundle-assembly-plan")).toBeTruthy();
    expect(screen.getByText("blocked synthesis bundle assembly unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-synthesis-bundle-assembly-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-synthesis-bundle")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-synthesis-source-packet")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-synthesis-evidence-map")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-synthesis-composition-plan")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-synthesis-quality-gate")).toBeTruthy();
    expect(
      screen.getByText(
        "synthesis bundle assembly planner must require worker synthesis handoff planning before synthesis bundles can be assembled",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Synthesis bundle assembly blockers:/)).toBeTruthy();
    expect(screen.getByText(/synthesis bundle assembly receipt writer/)).toBeTruthy();
    expect(screen.getByText(/synthesis source packet durable writer/)).toBeTruthy();
    expect(screen.getByText(/synthesis evidence map builder/)).toBeTruthy();
    expect(screen.getByText(/Synthesis bundle assembly receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/synthesis_bundle_id/)).toBeTruthy();
    expect(screen.getByText(/synthesis_evidence_map_id/)).toBeTruthy();
    expect(screen.getByText(/synthesis_quality_gate_id/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Final synthesis draft plan" }));

    await waitFor(() => expect(finalSynthesisDraftPlanMidnightOil).toHaveBeenCalled());
    expect(finalSynthesisDraftPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
      worker_cancellation_abandon_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
      }),
      worker_completion_finalization_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-completion-finalization-plan",
      }),
      worker_output_aggregation_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-output-aggregation-plan",
      }),
      worker_synthesis_handoff_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-synthesis-handoff-plan",
      }),
      synthesis_bundle_assembly_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-synthesis-bundle-assembly-plan",
      }),
    });
    expect(screen.getByText("Final synthesis draft receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-synthesis-draft-plan")).toBeTruthy();
    expect(screen.getByText("blocked final synthesis draft unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-synthesis-draft-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-synthesis-draft")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-synthesis-outline")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-synthesis-claim-map")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-synthesis-citation-map")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-synthesis-gap-list")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-synthesis-quality-report")).toBeTruthy();
    expect(
      screen.getByText(
        "final synthesis draft planner must require synthesis bundle assembly planning before any final draft can be created",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Final synthesis draft blockers:/)).toBeTruthy();
    expect(screen.getByText(/final synthesis draft receipt writer/)).toBeTruthy();
    expect(screen.getByText(/final synthesis citation map builder/)).toBeTruthy();
    expect(screen.getByText(/final synthesis quality report policy/)).toBeTruthy();
    expect(screen.getByText(/Final synthesis draft receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/final_synthesis_citation_map_id/)).toBeTruthy();
    expect(screen.getByText(/final_synthesis_quality_report_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", { name: "Final HTML artifact assembly plan" }),
    );

    await waitFor(() => expect(finalHtmlArtifactAssemblyPlanMidnightOil).toHaveBeenCalled());
    expect(finalHtmlArtifactAssemblyPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
      worker_cancellation_abandon_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
      }),
      worker_completion_finalization_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-completion-finalization-plan",
      }),
      worker_output_aggregation_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-output-aggregation-plan",
      }),
      worker_synthesis_handoff_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-synthesis-handoff-plan",
      }),
      synthesis_bundle_assembly_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-synthesis-bundle-assembly-plan",
      }),
      final_synthesis_draft_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-synthesis-draft-plan",
      }),
    });
    expect(screen.getByText("Final HTML artifact assembly receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-html-artifact-assembly-plan")).toBeTruthy();
    expect(screen.getByText("blocked final html artifact assembly unimplemented")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-final-html-artifact-assembly-receipt"),
    ).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-html-artifact")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-html-asset")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-html-document")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-html-twin-notes-document")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-html-citation-index")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-html-export-manifest")).toBeTruthy();
    expect(
      screen.getByText(
        "final HTML artifact assembly planner must require final synthesis draft planning before any human-viewable HTML asset can be created",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Final HTML artifact assembly blockers:/)).toBeTruthy();
    expect(screen.getByText(/final HTML artifact assembly receipt writer/)).toBeTruthy();
    expect(screen.getByText(/final HTML document renderer/)).toBeTruthy();
    expect(screen.getByText(/twin note document linker/)).toBeTruthy();
    expect(screen.getByText(/Final HTML artifact assembly receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/final_html_document_id/)).toBeTruthy();
    expect(screen.getByText(/final_html_citation_index_id/)).toBeTruthy();
    expect(screen.getByText(/final_html_export_manifest_id/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Final artifact persistence plan" }));

    await waitFor(() => expect(finalArtifactPersistencePlanMidnightOil).toHaveBeenCalled());
    expect(finalArtifactPersistencePlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
      worker_cancellation_abandon_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
      }),
      worker_completion_finalization_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-completion-finalization-plan",
      }),
      worker_output_aggregation_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-output-aggregation-plan",
      }),
      worker_synthesis_handoff_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-synthesis-handoff-plan",
      }),
      synthesis_bundle_assembly_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-synthesis-bundle-assembly-plan",
      }),
      final_synthesis_draft_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-synthesis-draft-plan",
      }),
      final_html_artifact_assembly_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-html-artifact-assembly-plan",
      }),
    });
    expect(screen.getByText("Final artifact persistence receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-persistence-plan")).toBeTruthy();
    expect(screen.getByText("blocked final artifact persistence unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-persistence-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-persisted-final-artifact")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-information-asset")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-hosted-html-asset")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-account-asset-binding")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-twin-notes-binding")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-citation-index-binding")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-graph-node")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-graph-edge-set")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-ledger-entry")).toBeTruthy();
    expect(
      screen.getByText(
        "final artifact persistence planner must require final HTML artifact assembly planning before any hosted information asset can be persisted",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Final artifact persistence blockers:/)).toBeTruthy();
    expect(screen.getByText(/information asset durable writer/)).toBeTruthy();
    expect(screen.getByText(/hosted HTML asset storage adapter/)).toBeTruthy();
    expect(screen.getByText(/artifact graph node writer/)).toBeTruthy();
    expect(screen.getByText(/Final artifact persistence receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/hosted_html_asset_id/)).toBeTruthy();
    expect(screen.getByText(/graph_node_id/)).toBeTruthy();
    expect(screen.getByText(/artifact_ledger_entry_id/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Final artifact graph commit plan" }));

    await waitFor(() => expect(finalArtifactGraphCommitPlanMidnightOil).toHaveBeenCalled());
    expect(finalArtifactGraphCommitPlanMidnightOil).toHaveBeenCalledWith({
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
      repository_transaction_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-transaction-plan",
      }),
      repository_commit_rollback_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-repository-commit-rollback-plan",
      }),
      worker_dispatch_lease_heartbeat_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-dispatch-lease-heartbeat-plan",
      }),
      worker_cancellation_abandon_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-cancellation-abandon-plan",
      }),
      worker_completion_finalization_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-completion-finalization-plan",
      }),
      worker_output_aggregation_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-output-aggregation-plan",
      }),
      worker_synthesis_handoff_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-worker-synthesis-handoff-plan",
      }),
      synthesis_bundle_assembly_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-synthesis-bundle-assembly-plan",
      }),
      final_synthesis_draft_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-synthesis-draft-plan",
      }),
      final_html_artifact_assembly_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-html-artifact-assembly-plan",
      }),
      final_artifact_persistence_plan_receipt: expect.objectContaining({
        receipt_id: "midnight-oil-test-final-artifact-persistence-plan",
      }),
    });
    expect(screen.getByText("Final artifact graph commit receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-graph-commit-plan")).toBeTruthy();
    expect(screen.getByText("blocked final artifact graph commit unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-graph-commit-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-graph-commit")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-graph-transaction")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-graph-snapshot")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-graph-lineage-index")).toBeTruthy();
    expect(
      screen.getByText(
        "final artifact graph commit planner must require final artifact persistence planning before any graph commit can be written",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Final artifact graph commit blockers:/)).toBeTruthy();
    expect(screen.getByText(/graph transaction writer/)).toBeTruthy();
    expect(screen.getByText(/graph node commit writer/)).toBeTruthy();
    expect(screen.getByText(/graph snapshot writer/)).toBeTruthy();
    expect(screen.getByText(/Final artifact graph commit receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/graph_transaction_id/)).toBeTruthy();
    expect(screen.getByText(/graph_snapshot_id/)).toBeTruthy();
    expect(screen.getByText(/graph_lineage_index_id/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Final artifact publish plan" }));

    await waitFor(() => expect(finalArtifactPublishPlanMidnightOil).toHaveBeenCalled());
    expect(finalArtifactPublishPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        approval_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-approval-receipt",
        }),
        runner_handoff: expect.objectContaining({
          handoff_id: "midnight-oil-test-runner-handoff",
        }),
        final_artifact_persistence_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-artifact-persistence-plan",
        }),
        final_artifact_graph_commit_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-artifact-graph-commit-plan",
        }),
      }),
    );
    expect(screen.getByText("Final artifact publish receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-publish-plan")).toBeTruthy();
    expect(screen.getByText("blocked final artifact publish unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-publish-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-publish-transaction")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-published-information-asset")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-account-visible-asset")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-reading-workspace-entry")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-twin-notes-workspace-entry")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-search-index-entry")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-private-read-url")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-publish-notification")).toBeTruthy();
    expect(
      screen.getByText(
        "final artifact publish planner must require final artifact graph commit planning before any account-visible artifact can be published",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Final artifact publish blockers:/)).toBeTruthy();
    expect(screen.getByText(/publish transaction writer/)).toBeTruthy();
    expect(screen.getByText(/reading workspace entry writer/)).toBeTruthy();
    expect(screen.getByText(/private read URL writer/)).toBeTruthy();
    expect(screen.getByText(/Final artifact publish receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/account_visible_asset_id/)).toBeTruthy();
    expect(screen.getByText(/reading_workspace_entry_id/)).toBeTruthy();
    expect(screen.getByText(/private_read_url_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", { name: "Final artifact completion finalization plan" }),
    );

    await waitFor(() =>
      expect(finalArtifactCompletionFinalizationPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(finalArtifactCompletionFinalizationPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        approval_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-approval-receipt",
        }),
        runner_handoff: expect.objectContaining({
          handoff_id: "midnight-oil-test-runner-handoff",
        }),
        final_artifact_graph_commit_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-artifact-graph-commit-plan",
        }),
        final_artifact_publish_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-artifact-publish-plan",
        }),
      }),
    );
    expect(screen.getByText("Final artifact completion finalization receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-final-artifact-completion-finalization-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked final artifact completion finalization unimplemented"),
    ).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-completion-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-finalization-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-completion-record")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-final-artifact-finalization-transaction"),
    ).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-archive-manifest")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-final-artifact-operator-handoff-summary"),
    ).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-delivery-status")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-artifact-quality-attestation")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-final-artifact-completion-audit-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "final artifact completion finalization planner must require final artifact publish planning before any completion record can be written",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Final artifact completion finalization blockers:/)).toBeTruthy();
    expect(screen.getByText(/final artifact completion receipt writer/)).toBeTruthy();
    expect(screen.getByText(/artifact archive manifest writer/)).toBeTruthy();
    expect(screen.getByText(/quality attestation writer/)).toBeTruthy();
    expect(
      screen.getByText(/Final artifact completion finalization receipt fields:/),
    ).toBeTruthy();
    expect(screen.getByText(/completion_record_id/)).toBeTruthy();
    expect(screen.getByText(/delivery_status_id/)).toBeTruthy();
    expect(screen.getByText(/quality_attestation_id/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Final run closure plan" }));

    await waitFor(() => expect(finalRunClosurePlanMidnightOil).toHaveBeenCalled());
    expect(finalRunClosurePlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        approval_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-approval-receipt",
        }),
        final_artifact_publish_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-artifact-publish-plan",
        }),
        final_artifact_completion_finalization_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-artifact-completion-finalization-plan",
        }),
      }),
    );
    expect(screen.getByText("Final run closure receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-run-closure-plan")).toBeTruthy();
    expect(screen.getByText("blocked final run closure unimplemented")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-final-run-closure-receipt")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-run-closeout-record")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-delivery-ledger-entry")).toBeTruthy();
    expect(screen.getAllByText("midnight-oil-test-workspace-delivery-card").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("midnight-oil-test-run-retention-manifest")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-model-usage-rollup")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-source-lineage-archive")).toBeTruthy();
    expect(
      screen.getByText(
        "final run closure planner must require final artifact completion finalization planning before any run closeout can be written",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Final run closure blockers:/)).toBeTruthy();
    expect(screen.getByText(/operator delivery ledger writer/)).toBeTruthy();
    expect(screen.getByText(/workspace delivery card writer/)).toBeTruthy();
    expect(screen.getByText(/model usage rollup writer/)).toBeTruthy();
    expect(screen.getByText(/Final run closure receipt fields:/)).toBeTruthy();
    expect(screen.getByText(/run_closeout_record_id/)).toBeTruthy();
    expect(screen.getByText(/operator_delivery_ledger_entry_id/)).toBeTruthy();
    expect(screen.getByText(/source_lineage_archive_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", {
        name: "Operator notification delivery readiness plan",
      }),
    );

    await waitFor(() =>
      expect(operatorNotificationDeliveryReadinessPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(operatorNotificationDeliveryReadinessPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        final_artifact_completion_finalization_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-artifact-completion-finalization-plan",
        }),
        final_run_closure_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-run-closure-plan",
        }),
      }),
    );
    expect(
      screen.getByText("Operator notification delivery readiness receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-readiness-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked operator notification delivery readiness unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-readiness-receipt"),
    ).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-notification-dispatch")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-notification-payload")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-delivery-channel-policy")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-notification-template")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-notification-audit-entry")).toBeTruthy();
    expect(
      screen.getByText(
        "operator notification delivery readiness planner must require final run closure planning before any notification dispatch can be written",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Operator notification delivery readiness blockers:/),
    ).toBeTruthy();
    expect(screen.getByText(/operator notification payload writer/)).toBeTruthy();
    expect(screen.getByText(/operator notification template writer/)).toBeTruthy();
    expect(
      screen.getByText(/Operator notification delivery readiness receipt fields:/),
    ).toBeTruthy();
    expect(screen.getByText(/operator_notification_dispatch_id/)).toBeTruthy();
    expect(screen.getByText(/operator_notification_payload_id/)).toBeTruthy();
    expect(screen.getByText(/operator_delivery_channel_policy_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", {
        name: "Operator notification delivery apply plan",
      }),
    );

    await waitFor(() =>
      expect(operatorNotificationDeliveryApplyPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(operatorNotificationDeliveryApplyPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        final_run_closure_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-run-closure-plan",
        }),
        operator_notification_delivery_readiness_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-operator-notification-delivery-readiness-plan",
        }),
      }),
    );
    expect(screen.getByText("Operator notification delivery apply receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-apply-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked operator notification delivery apply unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-apply-receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-transaction"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-attempt"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-result"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-status"),
    ).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-notification-retry-policy")).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-notification-dead-letter")).toBeTruthy();
    expect(
      screen.getByText(
        "operator notification delivery apply planner must require notification readiness planning before any delivery transaction can be written",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Operator notification delivery apply blockers:/)).toBeTruthy();
    expect(screen.getByText(/operator notification delivery result writer/)).toBeTruthy();
    expect(screen.getByText(/operator notification delivery channel adapter/)).toBeTruthy();
    expect(
      screen.getByText(/Operator notification delivery apply receipt fields:/),
    ).toBeTruthy();
    expect(screen.getByText(/operator_notification_delivery_transaction_id/)).toBeTruthy();
    expect(screen.getByText(/operator_notification_delivery_attempt_id/)).toBeTruthy();
    expect(screen.getByText(/operator_notification_dead_letter_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", {
        name: "Operator notification delivery result reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(operatorNotificationDeliveryResultReconciliationPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(operatorNotificationDeliveryResultReconciliationPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        operator_notification_delivery_readiness_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-operator-notification-delivery-readiness-plan",
        }),
        operator_notification_delivery_apply_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-operator-notification-delivery-apply-plan",
        }),
      }),
    );
    expect(
      screen.getByText("Operator notification delivery result reconciliation receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator notification delivery result reconciliation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-notification-delivery-result-reconciliation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-outcome-record"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-notification-delivery-reconciliation-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-delivery-retry-decision"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-notification-dead-letter-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator notification delivery result reconciliation planner must require delivery apply planning before any delivery outcome can be reconciled",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Operator notification delivery result reconciliation blockers:/),
    ).toBeTruthy();
    expect(screen.getByText(/operator notification delivery retry decision writer/)).toBeTruthy();
    expect(screen.getByText(/operator notification dead-letter entry writer/)).toBeTruthy();
    expect(
      screen.getByText(/Operator notification delivery result reconciliation receipt fields:/),
    ).toBeTruthy();
    expect(screen.getByText(/operator_notification_delivery_outcome_record_id/)).toBeTruthy();
    expect(
      screen.getByText(/operator_notification_delivery_reconciliation_entry_id/),
    ).toBeTruthy();
    expect(screen.getByText(/operator_notification_dead_letter_entry_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", {
        name: "Operator delivery ledger reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(operatorDeliveryLedgerReconciliationPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(operatorDeliveryLedgerReconciliationPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        operator_notification_delivery_apply_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-operator-notification-delivery-apply-plan",
        }),
        operator_notification_delivery_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
          }),
      }),
    );
    expect(screen.getByText("Operator delivery ledger reconciliation receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-delivery-ledger-reconciliation-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked operator delivery ledger reconciliation unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-delivery-ledger-reconciliation-receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-delivery-ledger-result-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-delivery-ledger-status-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-delivery-ledger-retry-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-delivery-ledger-dead-letter-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator delivery ledger reconciliation planner must require notification delivery result reconciliation planning before ledger rows can be reconciled",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Operator delivery ledger reconciliation blockers:/)).toBeTruthy();
    expect(screen.getByText(/operator delivery ledger result entry writer/)).toBeTruthy();
    expect(screen.getByText(/operator delivery ledger dead-letter entry writer/)).toBeTruthy();
    expect(
      screen.getByText(/Operator delivery ledger reconciliation receipt fields:/),
    ).toBeTruthy();
    expect(screen.getByText(/operator_delivery_ledger_result_entry_id/)).toBeTruthy();
    expect(screen.getByText(/operator_delivery_ledger_status_entry_id/)).toBeTruthy();
    expect(screen.getByText(/operator_delivery_ledger_dead_letter_entry_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", {
        name: "Workspace delivery card reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(workspaceDeliveryCardReconciliationPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(workspaceDeliveryCardReconciliationPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        operator_notification_delivery_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-notification-delivery-result-reconciliation-plan",
          }),
        operator_delivery_ledger_reconciliation_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
        }),
      }),
    );
    expect(screen.getByText("Workspace delivery card reconciliation receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-workspace-delivery-card-reconciliation-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked workspace delivery card reconciliation unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-workspace-delivery-card-reconciliation-receipt"),
    ).toBeTruthy();
    expect(
      screen.getAllByText("midnight-oil-test-workspace-delivery-card").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("midnight-oil-test-workspace-delivery-card-result-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-workspace-delivery-card-status-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-workspace-delivery-card-notification-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-workspace-delivery-card-replay-guard"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "workspace delivery card reconciliation planner must require operator delivery ledger reconciliation planning before workspace delivery cards can be reconciled",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Workspace delivery card reconciliation blockers:/)).toBeTruthy();
    expect(screen.getByText(/workspace delivery card result entry writer/)).toBeTruthy();
    expect(screen.getByText(/workspace delivery card notification entry writer/)).toBeTruthy();
    expect(
      screen.getByText(/Workspace delivery card reconciliation receipt fields:/),
    ).toBeTruthy();
    expect(screen.getByText(/workspace_delivery_card_result_entry_id/)).toBeTruthy();
    expect(screen.getByText(/workspace_delivery_card_status_entry_id/)).toBeTruthy();
    expect(screen.getByText(/workspace_delivery_card_notification_entry_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", {
        name: "Delivery notification reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(deliveryNotificationReconciliationPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(deliveryNotificationReconciliationPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        launch_packet: expect.objectContaining({
          packet_id: "midnight-oil-test-launch-packet",
        }),
        operator_delivery_ledger_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id: "midnight-oil-test-operator-delivery-ledger-reconciliation-plan",
          }),
        workspace_delivery_card_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id: "midnight-oil-test-workspace-delivery-card-reconciliation-plan",
          }),
      }),
    );
    expect(screen.getByText("Delivery notification reconciliation receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-delivery-notification-reconciliation-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked delivery notification reconciliation unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-delivery-notification-reconciliation-receipt"),
    ).toBeTruthy();
    expect(screen.getAllByText("midnight-oil-test-delivery-notification").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText("midnight-oil-test-delivery-notification-status-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-delivery-notification-result-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-delivery-notification-operator-visible-event"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-delivery-notification-replay-guard"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "delivery notification reconciliation planner must require workspace delivery card reconciliation planning before delivery notifications can be reconciled",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Delivery notification reconciliation blockers:/)).toBeTruthy();
    expect(screen.getByText(/delivery notification result entry writer/)).toBeTruthy();
    expect(
      screen.getByText(/delivery notification operator visible event writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/Delivery notification reconciliation receipt fields:/),
    ).toBeTruthy();
    expect(screen.getByText(/delivery_notification_status_entry_id/)).toBeTruthy();
    expect(screen.getByText(/delivery_notification_result_entry_id/)).toBeTruthy();
    expect(
      screen.getByText(/delivery_notification_operator_visible_event_id/),
    ).toBeTruthy();

    await user.click(
      screen.getByRole("button", {
        name: "Retention billing reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(retentionBillingReconciliationPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(retentionBillingReconciliationPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        delivery_notification_reconciliation_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-delivery-notification-reconciliation-plan",
        }),
        final_run_closure_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-final-run-closure-plan",
        }),
      }),
    );
    expect(screen.getByText("Retention billing reconciliation receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-retention-billing-reconciliation-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked retention billing reconciliation unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-retention-billing-reconciliation-receipt"),
    ).toBeTruthy();
    expect(
      screen.getAllByText("midnight-oil-test-run-retention-manifest").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-billing-reconciliation").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("midnight-oil-test-model-usage-rollup").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getAllByText("midnight-oil-test-source-lineage-archive").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("midnight-oil-test-run-retention-manifest-status-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-billing-reconciliation-status-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-model-usage-rollup-reconciliation-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-source-lineage-archive-reconciliation-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "retention billing reconciliation planner must require delivery notification reconciliation planning before retention, billing, usage, or source lineage rows can be reconciled",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Retention billing reconciliation blockers:/)).toBeTruthy();
    expect(screen.getByText(/run retention manifest reconciliation receipt writer/)).toBeTruthy();
    expect(screen.getByText(/billing reconciliation status entry writer/)).toBeTruthy();
    expect(screen.getByText(/source lineage archive reconciliation writer/)).toBeTruthy();
    expect(
      screen.getByText(/Retention billing reconciliation receipt fields:/),
    ).toBeTruthy();
    expect(screen.getByText(/run_retention_manifest_id/)).toBeTruthy();
    expect(screen.getByText(/billing_reconciliation_id/)).toBeTruthy();
    expect(screen.getByText(/model_usage_rollup_reconciliation_entry_id/)).toBeTruthy();
    expect(screen.getByText(/source_lineage_archive_reconciliation_entry_id/)).toBeTruthy();

    await user.click(
      screen.getByRole("button", {
        name: "Final closeout archive reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(finalCloseoutArchiveReconciliationPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(finalCloseoutArchiveReconciliationPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        retention_billing_reconciliation_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-retention-billing-reconciliation-plan",
        }),
        delivery_notification_reconciliation_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-delivery-notification-reconciliation-plan",
        }),
      }),
    );
    expect(
      screen.getByText("Final closeout archive reconciliation receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-final-closeout-archive-reconciliation-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked final closeout archive reconciliation unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-final-closeout-archive-reconciliation-receipt"),
    ).toBeTruthy();
    expect(
      screen.getAllByText("midnight-oil-test-final-run-closure-receipt").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-run-closeout-record").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-final-artifact-archive-manifest").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-operator-handoff-summary").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-quality-attestation").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("midnight-oil-test-completion-audit-entry").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "final closeout archive reconciliation planner must require retention billing reconciliation planning before closeout archive rows can be reconciled",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Final closeout archive reconciliation blockers:/),
    ).toBeTruthy();
    expect(
      screen.getByText(/artifact archive manifest reconciliation writer/),
    ).toBeTruthy();
    expect(screen.getByText(/quality attestation reconciliation writer/)).toBeTruthy();
    expect(screen.getByText(/completion audit reconciliation writer/)).toBeTruthy();
    expect(
      screen.getByText(/Final closeout archive reconciliation receipt fields:/),
    ).toBeTruthy();
    expect(screen.getAllByText(/final_run_closure_receipt_id/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/artifact_archive_manifest_id/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/operator_handoff_summary_id/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/quality_attestation_id/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/completion_audit_entry_id/).length).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive handoff package plan",
      }),
    );

    await waitFor(() =>
      expect(operatorArchiveHandoffPackagePlanMidnightOil).toHaveBeenCalled(),
    );
    expect(operatorArchiveHandoffPackagePlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        final_closeout_archive_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id: "midnight-oil-test-final-closeout-archive-reconciliation-plan",
          }),
        retention_billing_reconciliation_plan_receipt: expect.objectContaining({
          receipt_id: "midnight-oil-test-retention-billing-reconciliation-plan",
        }),
      }),
    );
    expect(screen.getByText("Operator archive handoff package receipt")).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-handoff-package-plan"),
    ).toBeTruthy();
    expect(
      screen.getByText("blocked operator archive handoff package unimplemented"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-handoff-package-receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-package"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-manifest"),
    ).toBeTruthy();
    expect(screen.getByText("midnight-oil-test-operator-handoff-bundle")).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive handoff package planner must require final closeout archive reconciliation planning before operator archive handoff packages can be written",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/Operator archive handoff package blockers:/)).toBeTruthy();
    expect(screen.getByText(/operator archive package writer/)).toBeTruthy();
    expect(screen.getByText(/operator archive manifest writer/)).toBeTruthy();
    expect(screen.getByText(/operator handoff bundle writer/)).toBeTruthy();
    expect(
      screen.getByText(/Operator archive handoff package receipt fields:/),
    ).toBeTruthy();
    expect(
      screen.getAllByText(/final_closeout_archive_reconciliation_plan_receipt_id/)
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText(/operator_archive_manifest_id/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/operator_handoff_bundle_id/).length).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package result reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchiveHandoffPackageResultReconciliationPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchiveHandoffPackageResultReconciliationPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_handoff_package_plan_receipt:
          expect.objectContaining({
            receipt_id: "midnight-oil-test-operator-archive-handoff-package-plan",
          }),
        final_closeout_archive_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id: "midnight-oil-test-final-closeout-archive-reconciliation-plan",
          }),
      }),
    );
    expect(
      screen.getByText("Operator archive package result reconciliation receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive handoff package result reconciliation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-package-result-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-manifest-status-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-handoff-bundle-status-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive handoff package result reconciliation planner must require operator archive handoff package planning before package result rows can be reconciled",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Operator archive package result reconciliation blockers:/),
    ).toBeTruthy();
    expect(screen.getByText(/operator archive package result entry writer/)).toBeTruthy();
    expect(screen.getByText(/operator archive manifest status entry writer/)).toBeTruthy();
    expect(screen.getByText(/operator handoff bundle status entry writer/)).toBeTruthy();
    expect(
      screen.getByText(/Operator archive package result reconciliation receipt fields:/),
    ).toBeTruthy();
    expect(
      screen.getAllByText(/operator_archive_package_result_entry_id/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/operator_archive_manifest_status_entry_id/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/operator_handoff_bundle_status_entry_id/).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery audit plan",
      }),
    );

    await waitFor(() =>
      expect(operatorArchiveHandoffPackageDeliveryAuditPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(operatorArchiveHandoffPackageDeliveryAuditPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_handoff_package_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
          }),
        operator_archive_handoff_package_plan_receipt:
          expect.objectContaining({
            receipt_id: "midnight-oil-test-operator-archive-handoff-package-plan",
          }),
      }),
    );
    expect(
      screen.getByText("Operator archive package delivery audit receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive handoff package delivery audit unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-package-delivery-audit-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-manifest-delivery-audit-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-handoff-bundle-delivery-audit-entry"),
    ).toBeTruthy();
    expect(
      screen.getByText("midnight-oil-test-operator-archive-delivery-audit-evidence-bundle"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive handoff package delivery audit planner must require package result reconciliation planning before delivery audit rows can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Operator archive package delivery audit blockers:/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive package delivery audit entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive manifest delivery audit entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator handoff bundle delivery audit entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive delivery audit evidence bundle writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/Operator archive package delivery audit receipt fields:/),
    ).toBeTruthy();
    expect(
      screen.getAllByText(/operator_archive_package_delivery_audit_entry_id/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/operator_archive_manifest_delivery_audit_entry_id/)
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/operator_archive_delivery_audit_evidence_bundle_id/)
        .length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery audit result reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_handoff_package_delivery_audit_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-handoff-package-delivery-audit-plan",
          }),
        operator_archive_handoff_package_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-handoff-package-result-reconciliation-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery audit result reconciliation receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive handoff package delivery audit result reconciliation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-audit-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-manifest-delivery-audit-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-handoff-bundle-delivery-audit-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-delivery-audit-evidence-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive handoff package delivery audit result reconciliation planner must require delivery audit planning before audit result rows can be reconciled",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery audit result reconciliation blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive package delivery audit result entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive manifest delivery audit status entry writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator handoff bundle delivery audit status entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive delivery audit evidence status entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery audit result reconciliation receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(/operator_archive_package_delivery_audit_result_entry_id/)
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_manifest_delivery_audit_status_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/operator_archive_delivery_audit_evidence_status_entry_id/)
        .length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report plan",
      }),
    );

    await waitFor(() =>
      expect(operatorArchivePackageDeliveryReportPlanMidnightOil).toHaveBeenCalled(),
    );
    expect(operatorArchivePackageDeliveryReportPlanMidnightOil).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-plan",
          }),
        operator_archive_handoff_package_delivery_audit_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-handoff-package-delivery-audit-plan",
          }),
      }),
    );
    expect(
      screen.getByText("Operator archive package delivery report receipt"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-manifest-delivery-report-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-handoff-bundle-delivery-report-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-delivery-report-evidence-bundle",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report planner must require delivery audit result reconciliation planning before delivery report rows can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Operator archive package delivery report blockers:/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive package delivery report receipt writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive package delivery report entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive manifest delivery report entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator handoff bundle delivery report entry writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/operator archive delivery report evidence bundle writer/),
    ).toBeTruthy();
    expect(
      screen.getByText(/Operator archive package delivery report receipt fields:/),
    ).toBeTruthy();
    expect(
      screen.getAllByText(/operator_archive_package_delivery_report_receipt_id/)
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/operator_archive_package_delivery_report_entry_id/)
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/operator_archive_delivery_report_evidence_bundle_id/)
        .length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report result reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportResultReconciliationPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportResultReconciliationPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-plan",
          }),
        operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-handoff-package-delivery-audit-result-reconciliation-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report result reconciliation receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report result reconciliation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-manifest-delivery-report-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-handoff-bundle-delivery-report-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-delivery-report-evidence-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report result reconciliation planner must require delivery report planning before report result rows can be reconciled",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report result reconciliation blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report result reconciliation receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report result entry writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive manifest delivery report status entry writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator handoff bundle delivery report status entry writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report result reconciliation receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_manifest_delivery_report_status_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/operator_archive_delivery_report_evidence_status_entry_id/)
        .length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report notification readiness plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportNotificationReadinessPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportNotificationReadinessPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
          }),
        operator_archive_package_delivery_report_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report notification readiness receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report notification readiness unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-payload",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-channel-policy",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-audit",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report notification readiness planner must require report result reconciliation planning before notification payloads can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report notification readiness blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report notification readiness receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report notification payload writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report notification channel policy writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report notification readiness receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_notification_payload_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_notification_channel_policy_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_notification_audit_id/,
      ).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report notification result reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_notification_readiness_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-plan",
          }),
        operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-result-reconciliation-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report notification result reconciliation receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report notification result reconciliation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-notification-audit-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report notification result reconciliation planner must require notification readiness planning before notification result rows can be reconciled",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report notification result reconciliation blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report notification result reconciliation receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report notification result entry writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report notification result reconciliation receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_notification_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_notification_status_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_notification_audit_status_entry_id/,
      ).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report delivery confirmation plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportDeliveryConfirmationPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-plan",
          }),
        operator_archive_package_delivery_report_notification_readiness_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-notification-readiness-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report delivery confirmation receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report delivery confirmation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-audit-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report delivery confirmation planner must require notification result reconciliation planning before delivery confirmation rows can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report delivery confirmation blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report delivery confirmation receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report delivery confirmation entry writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report delivery confirmation receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_delivery_confirmation_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_delivery_confirmation_status_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_delivery_confirmation_audit_entry_id/,
      ).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report delivery confirmation result reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_delivery_confirmation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-plan",
          }),
        operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-notification-result-reconciliation-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report delivery confirmation result reconciliation receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report delivery confirmation result reconciliation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-status-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-audit-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report delivery confirmation result reconciliation planner must require delivery confirmation planning before confirmation result rows can be reconciled",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report delivery confirmation result reconciliation blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report delivery confirmation result reconciliation receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report delivery confirmation result entry writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report delivery confirmation result reconciliation receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_delivery_confirmation_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report final operator acknowledgement plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
          }),
        operator_archive_package_delivery_report_delivery_confirmation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report final operator acknowledgement receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report final operator acknowledgement unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-audit-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report final operator acknowledgement planner must require delivery confirmation result reconciliation before acknowledgement rows can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report final operator acknowledgement blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report final operator acknowledgement receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report final operator acknowledgement entry writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report final operator acknowledgement receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_acknowledgement_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_id/,
      ).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report acknowledgement result reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-plan",
          }),
        operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report acknowledgement result reconciliation receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report acknowledgement result reconciliation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-status-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-audit-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report acknowledgement result reconciliation planner must require final operator acknowledgement before acknowledgement result rows can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report acknowledgement result reconciliation blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report acknowledgement result reconciliation receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report acknowledgement result reconciliation receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_acknowledgement_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_acknowledgement_status_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_acknowledgement_audit_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report final closeout acknowledgement plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan",
          }),
        operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-final-operator-acknowledgement-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report final closeout acknowledgement receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report final closeout acknowledgement unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-audit-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report final closeout acknowledgement planner must require acknowledgement result reconciliation before final closeout acknowledgement rows can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report final closeout acknowledgement blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report final closeout acknowledgement receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report final closeout acknowledgement receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_id/,
      ).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report final operator delivery closeout plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-plan",
          }),
        operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report final operator delivery closeout receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report final operator delivery closeout unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-status-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-audit-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report final operator delivery closeout planner must require final closeout acknowledgement before final operator delivery closeout rows can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report final operator delivery closeout blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report final operator delivery closeout receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report final operator delivery closeout receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_id/,
      ).length,
    ).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("button", {
        name: "Operator archive package delivery report final operator delivery closeout result reconciliation plan",
      }),
    );

    await waitFor(() =>
      expect(
        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanMidnightOil,
      ).toHaveBeenCalled(),
    );
    expect(
      operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanMidnightOil,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        operator_archive_package_delivery_report_final_operator_delivery_closeout_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-plan",
          }),
        operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt:
          expect.objectContaining({
            receipt_id:
              "midnight-oil-test-operator-archive-package-delivery-report-final-closeout-acknowledgement-plan",
          }),
      }),
    );
    expect(
      screen.getByText(
        "Operator archive package delivery report final operator delivery closeout result reconciliation receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-result-reconciliation-plan",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "blocked operator archive package delivery report final operator delivery closeout result reconciliation unimplemented",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-result-reconciliation-receipt",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-status-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "midnight-oil-test-operator-archive-package-delivery-report-final-operator-delivery-closeout-audit-result-entry",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "operator archive package delivery report final operator delivery closeout result reconciliation planner must require final operator delivery closeout planning before final operator delivery closeout result rows can be planned",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report final operator delivery closeout result reconciliation blockers:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /operator archive package delivery report final operator delivery closeout result reconciliation receipt writer/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Operator archive package delivery report final operator delivery closeout result reconciliation receipt fields:/,
      ),
    ).toBeTruthy();
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_delivery_closeout_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_delivery_closeout_status_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        /operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_result_entry_id/,
      ).length,
    ).toBeGreaterThan(0);
  }, 15000);
});
