import { API_BASE, apiFetch } from "../lib/api";

export type MidnightOilRouteMode =
  | "auto_quality"
  | "auto_balanced"
  | "auto_cost"
  | "auto_latency"
  | "manual";

export type MidnightOilSourcePolicy = "arxiv" | "substack" | "web" | "operator_corpus";

export interface MidnightOilRequest {
  goal: string;
  work_minutes: number;
  price_ceiling_usd: number;
  route_mode: MidnightOilRouteMode;
  source_policy: MidnightOilSourcePolicy[];
  deliverable: "html_research_asset";
  operator_acknowledged_spend: boolean;
}

export interface MidnightOilRolePlan {
  role: "planner" | "gatherer" | "verifier" | "synthesizer";
  budget_usd: number;
  max_minutes: number;
  route_mode: MidnightOilRouteMode;
  route_receipt_required: boolean;
  source_receipts_required: boolean;
  planned_route_receipt_id: string;
}

export interface MidnightOilArtifactContract {
  final_format: "html";
  pdf_allowed: boolean;
  antiek_information_asset: boolean;
  twin_note_document_required: boolean;
  route_receipt_links_required: boolean;
  source_receipt_links_required: boolean;
}

export interface MidnightOilLaunchPacket {
  packet_id: string;
  run_id: string;
  goal: string;
  work_minutes: number;
  price_ceiling_usd: number;
  planned_budget_usd: number;
  unallocated_budget_usd: number;
  route_mode: MidnightOilRouteMode;
  source_policy: MidnightOilSourcePolicy[];
  deliverable: "html_research_asset";
  artifact_contract: MidnightOilArtifactContract;
  role_count: number;
  role_route_receipt_ids: string[];
  source_receipts_required: boolean;
  route_receipts_required: boolean;
  dispatch_allowed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  launch_notes: string[];
}

export interface MidnightOilApprovalReceipt {
  receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  operator_acknowledged_spend: boolean;
  approved_price_ceiling_usd: number;
  approved_work_minutes: number;
  approved_route_mode: MidnightOilRouteMode;
  approved_source_policy: MidnightOilSourcePolicy[];
  approved_deliverable: "html_research_asset";
  planned_budget_usd: number;
  unallocated_budget_usd: number;
  approval_scope: "preflight_launch_packet_only";
  runner_apply_required: boolean;
  dispatch_allowed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  receipt_notes: string[];
}

export interface MidnightOilRunnerHandoff {
  handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "ready_for_runner_apply";
  approved_price_ceiling_usd: number;
  planned_budget_usd: number;
  unallocated_budget_usd: number;
  role_route_receipt_ids: string[];
  prerequisite_receipt_ids: string[];
  dispatch_ready: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  graph_mutated: boolean;
  handoff_notes: string[];
}

export interface MidnightOilAppliedRunReceipt {
  receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "planned_not_dispatched";
  planned_role_count: number;
  planned_budget_usd: number;
  unallocated_budget_usd: number;
  planned_role_route_receipt_ids: string[];
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  applied_notes: string[];
}

export interface MidnightOilPreflight {
  accepted: boolean;
  denial_reason: string | null;
  run_id: string | null;
  goal: string;
  work_minutes: number;
  price_ceiling_usd: number;
  route_mode: MidnightOilRouteMode;
  source_policy: MidnightOilSourcePolicy[];
  deliverable: "html_research_asset";
  planned_budget_usd: number;
  unallocated_budget_usd: number;
  role_plans: MidnightOilRolePlan[];
  artifact_contract: MidnightOilArtifactContract;
  launch_packet: MidnightOilLaunchPacket | null;
  approval_receipt: MidnightOilApprovalReceipt | null;
  runner_handoff: MidnightOilRunnerHandoff | null;
  applied_run_receipt: MidnightOilAppliedRunReceipt | null;
  notes: string[];
}

export interface MidnightOilLiveRunActivationSettingsRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  requested_live_run_enabled: boolean;
  requested_price_ceiling_usd: number;
  requested_work_minutes: number;
}

export interface MidnightOilLiveRunActivationSettingsReceipt {
  receipt_id: string;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_live_run_activation_disabled";
  settings_scope: "midnight_oil_live_run_activation";
  requested_live_run_enabled: boolean;
  requested_price_ceiling_usd: number;
  requested_work_minutes: number;
  approved_price_ceiling_usd: number;
  approved_work_minutes: number;
  missing_controls: string[];
  blocker_reason: "live_run_activation_controls_missing";
  live_run_activation_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  settings_notes: string[];
}

export interface MidnightOilDryRunRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
}

export interface MidnightOilDispatchRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  live_dispatch_requested: boolean;
}

export interface MidnightOilDispatchReceipt {
  receipt_id: string;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_live_dispatch_disabled";
  live_dispatch_requested: boolean;
  blocker_reason: "live_dispatch_disabled";
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_notes: string[];
}

export interface MidnightOilActivationChecklistRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  live_run_activation_settings_receipt?: MidnightOilLiveRunActivationSettingsReceipt | null;
  dispatch_receipt: MidnightOilDispatchReceipt;
}

export interface MidnightOilActivationChecklistReceipt {
  receipt_id: string;
  dispatch_receipt_id: string;
  live_run_activation_settings_receipt_id: string | null;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "activation_blocked_controls_missing";
  completed_items: string[];
  missing_items: string[];
  dispatch_allowed: boolean;
  budget_reservation_allowed: boolean;
  provider_execution_allowed: boolean;
  retrieval_allowed: boolean;
  graph_mutation_allowed: boolean;
  final_artifact_allowed: boolean;
  checklist_notes: string[];
}

export interface MidnightOilBudgetReservationRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  dispatch_receipt: MidnightOilDispatchReceipt;
  activation_checklist_receipt: MidnightOilActivationChecklistReceipt;
}

export interface MidnightOilBudgetReservationReceipt {
  receipt_id: string;
  activation_checklist_receipt_id: string;
  dispatch_receipt_id: string;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_budget_reservation_disabled";
  requested_reservation_usd: number;
  approved_price_ceiling_usd: number;
  planned_budget_usd: number;
  unallocated_budget_usd: number;
  blocker_reason: "budget_reservation_provider_missing";
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  dispatch_performed: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  reservation_notes: string[];
}

export interface MidnightOilProviderRouteRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  dispatch_receipt: MidnightOilDispatchReceipt;
  activation_checklist_receipt: MidnightOilActivationChecklistReceipt;
  budget_reservation_receipt: MidnightOilBudgetReservationReceipt;
}

export interface MidnightOilProviderRouteReceipt {
  receipt_id: string;
  budget_reservation_receipt_id: string;
  activation_checklist_receipt_id: string;
  dispatch_receipt_id: string;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_provider_route_executor_disabled";
  requested_route_count: number;
  planned_role_route_receipt_ids: string[];
  blocker_reason: "provider_route_executor_missing";
  route_executor_allowed: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  budget_reserved: boolean;
  dispatch_performed: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  provider_route_notes: string[];
}

export interface MidnightOilRetrievalRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  dispatch_receipt: MidnightOilDispatchReceipt;
  activation_checklist_receipt: MidnightOilActivationChecklistReceipt;
  budget_reservation_receipt: MidnightOilBudgetReservationReceipt;
  provider_route_receipt: MidnightOilProviderRouteReceipt;
}

export interface MidnightOilRetrievalReceipt {
  receipt_id: string;
  provider_route_receipt_id: string;
  budget_reservation_receipt_id: string;
  activation_checklist_receipt_id: string;
  dispatch_receipt_id: string;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_retrieval_executor_disabled";
  planned_source_policy: MidnightOilSourcePolicy[];
  planned_source_receipt_ids: string[];
  blocker_reason: "retrieval_executor_missing";
  retrieval_allowed: boolean;
  source_receipts_created: boolean;
  retrieval_performed: boolean;
  provider_calls_made: boolean;
  budget_reserved: boolean;
  dispatch_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  retrieval_notes: string[];
}

export interface MidnightOilGraphMutationRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  dispatch_receipt: MidnightOilDispatchReceipt;
  activation_checklist_receipt: MidnightOilActivationChecklistReceipt;
  budget_reservation_receipt: MidnightOilBudgetReservationReceipt;
  provider_route_receipt: MidnightOilProviderRouteReceipt;
  retrieval_receipt: MidnightOilRetrievalReceipt;
}

export interface MidnightOilGraphMutationReceipt {
  receipt_id: string;
  retrieval_receipt_id: string;
  provider_route_receipt_id: string;
  budget_reservation_receipt_id: string;
  activation_checklist_receipt_id: string;
  dispatch_receipt_id: string;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_graph_mutation_disabled";
  planned_graph_node_ids: string[];
  planned_graph_edge_ids: string[];
  blocker_reason: "graph_mutation_writer_missing";
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  source_receipts_created: boolean;
  retrieval_performed: boolean;
  provider_calls_made: boolean;
  budget_reserved: boolean;
  dispatch_performed: boolean;
  final_artifact_created: boolean;
  graph_notes: string[];
}

export interface MidnightOilFinalArtifactRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  dispatch_receipt: MidnightOilDispatchReceipt;
  activation_checklist_receipt: MidnightOilActivationChecklistReceipt;
  budget_reservation_receipt: MidnightOilBudgetReservationReceipt;
  provider_route_receipt: MidnightOilProviderRouteReceipt;
  retrieval_receipt: MidnightOilRetrievalReceipt;
  graph_mutation_receipt: MidnightOilGraphMutationReceipt;
}

export interface MidnightOilFinalArtifactReceipt {
  receipt_id: string;
  graph_mutation_receipt_id: string;
  retrieval_receipt_id: string;
  provider_route_receipt_id: string;
  budget_reservation_receipt_id: string;
  activation_checklist_receipt_id: string;
  dispatch_receipt_id: string;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_final_artifact_writer_disabled";
  planned_artifact_id: string;
  planned_twin_note_document_id: string;
  final_format: "html";
  pdf_allowed: boolean;
  blocker_reason: "final_html_artifact_writer_missing";
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  graph_mutated: boolean;
  source_receipts_created: boolean;
  retrieval_performed: boolean;
  provider_calls_made: boolean;
  budget_reserved: boolean;
  dispatch_performed: boolean;
  artifact_notes: string[];
}

export interface MidnightOilRunnerReadinessRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  applied_run_receipt: MidnightOilAppliedRunReceipt;
  live_run_activation_settings_receipt: MidnightOilLiveRunActivationSettingsReceipt;
  dispatch_receipt: MidnightOilDispatchReceipt;
  activation_checklist_receipt: MidnightOilActivationChecklistReceipt;
  budget_reservation_receipt: MidnightOilBudgetReservationReceipt;
  provider_route_receipt: MidnightOilProviderRouteReceipt;
  retrieval_receipt: MidnightOilRetrievalReceipt;
  graph_mutation_receipt: MidnightOilGraphMutationReceipt;
  final_artifact_receipt: MidnightOilFinalArtifactReceipt;
}

export interface MidnightOilRunnerReadinessReceipt {
  receipt_id: string;
  final_artifact_receipt_id: string;
  graph_mutation_receipt_id: string;
  retrieval_receipt_id: string;
  provider_route_receipt_id: string;
  budget_reservation_receipt_id: string;
  activation_checklist_receipt_id: string;
  live_run_activation_settings_receipt_id: string;
  dispatch_receipt_id: string;
  applied_run_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_runner_readiness_controls_missing";
  completed_receipt_ids: string[];
  remaining_blockers: string[];
  blocker_reason: "runner_readiness_controls_missing";
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  budget_reservation_allowed: boolean;
  provider_execution_allowed: boolean;
  retrieval_allowed: boolean;
  graph_mutation_allowed: boolean;
  final_artifact_allowed: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  readiness_notes: string[];
}

export type MidnightOilRunnerControlKey =
  | "budget_reservation_provider"
  | "model_provider_route_executor"
  | "retrieval_executor_source_receipts"
  | "graph_mutation_writer"
  | "final_html_artifact_writer"
  | "operator_live_dispatch_enablement";

export interface MidnightOilRunnerControlRequirement {
  control_key: MidnightOilRunnerControlKey;
  blocker: string;
  required_artifact: string;
  implementation_status: "missing";
  live_enablement_allowed: boolean;
}

export interface MidnightOilRunnerControlPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_readiness_receipt: MidnightOilRunnerReadinessReceipt;
  requested_control_scope?: MidnightOilRunnerControlKey[];
}

export interface MidnightOilRunnerControlPlanReceipt {
  receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_runner_controls_unimplemented";
  requested_control_scope: MidnightOilRunnerControlKey[];
  required_control_order: MidnightOilRunnerControlKey[];
  implementation_requirements: MidnightOilRunnerControlRequirement[];
  remaining_blockers: string[];
  blocker_reason: "runner_controls_unimplemented";
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  budget_reservation_allowed: boolean;
  provider_execution_allowed: boolean;
  retrieval_allowed: boolean;
  graph_mutation_allowed: boolean;
  final_artifact_allowed: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  control_plan_notes: string[];
}

export interface MidnightOilBudgetProviderAdapterPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
}

export interface MidnightOilBudgetProviderAdapterPlanReceipt {
  receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_budget_provider_adapter_unimplemented";
  adapter_key: "budget_reservation_provider";
  planned_adapter_id: string;
  planned_ledger_id: string;
  idempotency_key: string;
  approved_price_ceiling_usd: number;
  planned_budget_usd: number;
  unallocated_budget_usd: number;
  required_invariants: string[];
  required_ledger_fields: string[];
  blocker_reason: "budget_provider_adapter_unimplemented";
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  provider_execution_allowed: boolean;
  retrieval_allowed: boolean;
  graph_mutation_allowed: boolean;
  final_artifact_allowed: boolean;
  dispatch_performed: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilProviderExecutorAdapterPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
}

export interface MidnightOilProviderExecutorAdapterPlanReceipt {
  receipt_id: string;
  runner_control_plan_receipt_id: string;
  budget_provider_adapter_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_provider_executor_adapter_unimplemented";
  adapter_key: "model_provider_route_executor";
  planned_executor_id: string;
  planned_route_ledger_id: string;
  planned_role_route_receipt_ids: string[];
  requested_route_count: number;
  route_mode: MidnightOilRouteMode;
  provider_policy: "operator_configured_models_only";
  required_invariants: string[];
  required_route_receipt_fields: string[];
  blocker_reason: "provider_executor_adapter_unimplemented";
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  retrieval_allowed: boolean;
  graph_mutation_allowed: boolean;
  final_artifact_allowed: boolean;
  dispatch_performed: boolean;
  retrieval_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilRetrievalAdapterPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
}

export interface MidnightOilRetrievalAdapterPlanReceipt {
  receipt_id: string;
  runner_control_plan_receipt_id: string;
  budget_provider_adapter_plan_receipt_id: string;
  provider_executor_adapter_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_retrieval_adapter_unimplemented";
  adapter_key: "retrieval_executor_source_receipts";
  planned_executor_id: string;
  planned_source_ledger_id: string;
  planned_source_policy: MidnightOilSourcePolicy[];
  planned_source_receipt_ids: string[];
  requested_source_count: number;
  required_invariants: string[];
  required_source_receipt_fields: string[];
  blocker_reason: "retrieval_adapter_unimplemented";
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  graph_mutation_allowed: boolean;
  final_artifact_allowed: boolean;
  dispatch_performed: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilGraphAdapterPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
}

export interface MidnightOilGraphAdapterPlanReceipt {
  receipt_id: string;
  runner_control_plan_receipt_id: string;
  budget_provider_adapter_plan_receipt_id: string;
  provider_executor_adapter_plan_receipt_id: string;
  retrieval_adapter_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_graph_adapter_unimplemented";
  adapter_key: "graph_mutation_writer";
  planned_writer_id: string;
  planned_graph_ledger_id: string;
  planned_graph_node_ids: string[];
  planned_graph_edge_ids: string[];
  required_invariants: string[];
  required_graph_receipt_fields: string[];
  blocker_reason: "graph_adapter_unimplemented";
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  source_receipts_created: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  final_artifact_allowed: boolean;
  dispatch_performed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalArtifactAdapterPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
}

export interface MidnightOilFinalArtifactAdapterPlanReceipt {
  receipt_id: string;
  runner_control_plan_receipt_id: string;
  budget_provider_adapter_plan_receipt_id: string;
  provider_executor_adapter_plan_receipt_id: string;
  retrieval_adapter_plan_receipt_id: string;
  graph_adapter_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_final_artifact_adapter_unimplemented";
  adapter_key: "final_html_artifact_writer";
  planned_writer_id: string;
  planned_artifact_ledger_id: string;
  planned_artifact_id: string;
  planned_twin_note_document_id: string;
  final_format: "html";
  pdf_allowed: boolean;
  required_invariants: string[];
  required_artifact_receipt_fields: string[];
  blocker_reason: "final_artifact_adapter_unimplemented";
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  source_receipts_created: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  dispatch_performed: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorDispatchAdapterPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
}

export interface MidnightOilOperatorDispatchAdapterPlanReceipt {
  receipt_id: string;
  runner_control_plan_receipt_id: string;
  budget_provider_adapter_plan_receipt_id: string;
  provider_executor_adapter_plan_receipt_id: string;
  retrieval_adapter_plan_receipt_id: string;
  graph_adapter_plan_receipt_id: string;
  final_artifact_adapter_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_operator_dispatch_adapter_unimplemented";
  adapter_key: "operator_live_dispatch_enablement";
  planned_setting_id: string;
  planned_control_ledger_id: string;
  required_invariants: string[];
  required_dispatch_enablement_fields: string[];
  blocker_reason: "operator_dispatch_adapter_unimplemented";
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilControlLedgerAdapterPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
}

export interface MidnightOilControlLedgerAdapterPlanReceipt {
  receipt_id: string;
  operator_dispatch_adapter_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  budget_provider_adapter_plan_receipt_id: string;
  provider_executor_adapter_plan_receipt_id: string;
  retrieval_adapter_plan_receipt_id: string;
  graph_adapter_plan_receipt_id: string;
  final_artifact_adapter_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_control_ledger_adapter_unimplemented";
  adapter_key: "operator_dispatch_control_ledger";
  planned_setting_id: string;
  planned_control_ledger_id: string;
  planned_audit_log_id: string;
  planned_rollback_receipt_id: string;
  required_invariants: string[];
  required_control_ledger_fields: string[];
  required_rollback_receipt_fields: string[];
  blocker_reason: "control_ledger_adapter_unimplemented";
  control_ledger_persistence_allowed: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilControlLedgerPersistencePlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
}

export interface MidnightOilControlLedgerPersistencePlanReceipt {
  receipt_id: string;
  control_ledger_adapter_plan_receipt_id: string;
  operator_dispatch_adapter_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_control_ledger_persistence_unimplemented";
  adapter_key: "operator_dispatch_control_ledger_persistence";
  planned_repository_id: string;
  planned_transaction_id: string;
  planned_setting_id: string;
  planned_control_ledger_id: string;
  planned_audit_log_id: string;
  planned_rollback_receipt_id: string;
  required_storage_tables: string[];
  required_transaction_invariants: string[];
  required_apply_fields: string[];
  blocker_reason: "control_ledger_persistence_unimplemented";
  persistence_adapter_allowed: boolean;
  control_ledger_persistence_allowed: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilControlLedgerPersistenceApplyPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
}

export interface MidnightOilControlLedgerPersistenceApplyPlanReceipt {
  receipt_id: string;
  control_ledger_persistence_plan_receipt_id: string;
  control_ledger_adapter_plan_receipt_id: string;
  operator_dispatch_adapter_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_control_ledger_persistence_apply_unimplemented";
  adapter_key: "operator_dispatch_control_ledger_persistence_apply";
  planned_repository_id: string;
  planned_transaction_id: string;
  planned_commit_receipt_id: string;
  planned_content_digest: string;
  planned_setting_id: string;
  planned_control_ledger_id: string;
  planned_audit_log_id: string;
  planned_rollback_receipt_id: string;
  required_commit_invariants: string[];
  required_commit_receipt_fields: string[];
  blocker_reason: "control_ledger_persistence_apply_unimplemented";
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_persistence_allowed: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorDispatchActivationReadinessPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
}

export interface MidnightOilOperatorDispatchActivationReadinessPlanReceipt {
  receipt_id: string;
  control_ledger_persistence_apply_plan_receipt_id: string;
  control_ledger_persistence_plan_receipt_id: string;
  control_ledger_adapter_plan_receipt_id: string;
  operator_dispatch_adapter_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_operator_dispatch_activation_readiness_unimplemented";
  adapter_key: "operator_dispatch_activation_readiness";
  planned_commit_receipt_id: string;
  planned_activation_readiness_receipt_id: string;
  planned_dispatch_enablement_id: string;
  planned_repository_id: string;
  planned_transaction_id: string;
  required_activation_invariants: string[];
  required_activation_receipt_fields: string[];
  readiness_blockers: string[];
  blocker_reason: "operator_dispatch_activation_readiness_unimplemented";
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilLiveDispatchFinalEnablementPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
}

export interface MidnightOilLiveDispatchFinalEnablementPlanReceipt {
  receipt_id: string;
  operator_dispatch_activation_readiness_plan_receipt_id: string;
  control_ledger_persistence_apply_plan_receipt_id: string;
  control_ledger_persistence_plan_receipt_id: string;
  control_ledger_adapter_plan_receipt_id: string;
  operator_dispatch_adapter_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_live_dispatch_final_enablement_unimplemented";
  adapter_key: "live_dispatch_final_enablement";
  planned_activation_readiness_receipt_id: string;
  planned_dispatch_enablement_id: string;
  planned_live_dispatch_receipt_id: string;
  planned_runner_dispatch_id: string;
  readiness_blockers: string[];
  required_enablement_invariants: string[];
  required_enablement_receipt_fields: string[];
  blocker_reason: "live_dispatch_final_enablement_unimplemented";
  final_enablement_allowed: boolean;
  live_dispatch_enabled: boolean;
  live_dispatch_ready: boolean;
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilLiveDispatchFinalEnablementApplyPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
}

export interface MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt {
  receipt_id: string;
  live_dispatch_final_enablement_plan_receipt_id: string;
  operator_dispatch_activation_readiness_plan_receipt_id: string;
  control_ledger_persistence_apply_plan_receipt_id: string;
  control_ledger_persistence_plan_receipt_id: string;
  control_ledger_adapter_plan_receipt_id: string;
  operator_dispatch_adapter_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_live_dispatch_final_enablement_apply_unimplemented";
  adapter_key: "live_dispatch_final_enablement_apply";
  planned_activation_readiness_receipt_id: string;
  planned_dispatch_enablement_id: string;
  planned_live_dispatch_receipt_id: string;
  planned_runner_dispatch_id: string;
  planned_apply_receipt_id: string;
  planned_idempotency_key: string;
  planned_repository_id: string;
  planned_transaction_id: string;
  apply_blockers: string[];
  required_apply_invariants: string[];
  required_apply_receipt_fields: string[];
  blocker_reason: "live_dispatch_final_enablement_apply_unimplemented";
  final_enablement_apply_allowed: boolean;
  final_enablement_allowed: boolean;
  live_dispatch_enabled: boolean;
  live_dispatch_ready: boolean;
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilRunnerDispatchSchedulerPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
}

export interface MidnightOilRunnerDispatchSchedulerPlanReceipt {
  receipt_id: string;
  live_dispatch_final_enablement_apply_plan_receipt_id: string;
  live_dispatch_final_enablement_plan_receipt_id: string;
  operator_dispatch_activation_readiness_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_runner_dispatch_scheduler_unimplemented";
  adapter_key: "runner_dispatch_scheduler";
  planned_scheduler_job_id: string;
  planned_queue_id: string;
  planned_runner_dispatch_id: string;
  planned_live_dispatch_receipt_id: string;
  planned_idempotency_key: string;
  planned_apply_receipt_id: string;
  scheduler_blockers: string[];
  required_scheduler_invariants: string[];
  required_scheduler_receipt_fields: string[];
  blocker_reason: "runner_dispatch_scheduler_unimplemented";
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  final_enablement_apply_allowed: boolean;
  final_enablement_allowed: boolean;
  live_dispatch_enabled: boolean;
  live_dispatch_ready: boolean;
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilRunnerDispatchWorkerBootstrapPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
  runner_dispatch_scheduler_plan_receipt: MidnightOilRunnerDispatchSchedulerPlanReceipt;
}

export interface MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt {
  receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  live_dispatch_final_enablement_apply_plan_receipt_id: string;
  live_dispatch_final_enablement_plan_receipt_id: string;
  operator_dispatch_activation_readiness_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_runner_dispatch_worker_bootstrap_unimplemented";
  adapter_key: "runner_dispatch_worker_bootstrap";
  planned_worker_bootstrap_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_retry_policy_id: string;
  planned_dead_letter_queue_id: string;
  planned_scheduler_job_id: string;
  planned_queue_id: string;
  planned_runner_dispatch_id: string;
  planned_live_dispatch_receipt_id: string;
  planned_idempotency_key: string;
  worker_bootstrap_blockers: string[];
  required_worker_invariants: string[];
  required_worker_receipt_fields: string[];
  blocker_reason: "runner_dispatch_worker_bootstrap_unimplemented";
  worker_bootstrap_allowed: boolean;
  worker_bootstrap_created: boolean;
  worker_started: boolean;
  lease_policy_created: boolean;
  retry_policy_created: boolean;
  dead_letter_queue_created: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  final_enablement_apply_allowed: boolean;
  final_enablement_allowed: boolean;
  live_dispatch_enabled: boolean;
  live_dispatch_ready: boolean;
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilSchedulerLeaseRetryPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
  runner_dispatch_scheduler_plan_receipt: MidnightOilRunnerDispatchSchedulerPlanReceipt;
  runner_dispatch_worker_bootstrap_plan_receipt: MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt;
}

export interface MidnightOilSchedulerLeaseRetryPlanReceipt {
  receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  live_dispatch_final_enablement_apply_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_scheduler_lease_retry_unimplemented";
  adapter_key: "scheduler_lease_retry";
  planned_lease_policy_id: string;
  planned_retry_policy_id: string;
  planned_dead_letter_queue_id: string;
  planned_visibility_timeout_seconds: number;
  planned_lease_ttl_seconds: number;
  planned_heartbeat_interval_seconds: number;
  planned_max_attempts: number;
  planned_backoff_policy: "exponential_jitter";
  planned_scheduler_job_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_live_dispatch_receipt_id: string;
  planned_idempotency_key: string;
  lease_retry_blockers: string[];
  required_lease_retry_invariants: string[];
  required_lease_retry_receipt_fields: string[];
  blocker_reason: "scheduler_lease_retry_unimplemented";
  lease_retry_allowed: boolean;
  lease_policy_created: boolean;
  retry_policy_created: boolean;
  dead_letter_queue_created: boolean;
  worker_bootstrap_allowed: boolean;
  worker_bootstrap_created: boolean;
  worker_started: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  final_enablement_apply_allowed: boolean;
  final_enablement_allowed: boolean;
  live_dispatch_enabled: boolean;
  live_dispatch_ready: boolean;
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilWorkerQueueClaimPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
  runner_dispatch_scheduler_plan_receipt: MidnightOilRunnerDispatchSchedulerPlanReceipt;
  runner_dispatch_worker_bootstrap_plan_receipt: MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt;
  scheduler_lease_retry_plan_receipt: MidnightOilSchedulerLeaseRetryPlanReceipt;
}

export interface MidnightOilWorkerQueueClaimPlanReceipt {
  receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  live_dispatch_final_enablement_apply_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_worker_queue_claim_unimplemented";
  adapter_key: "worker_queue_claim";
  planned_queue_claim_id: string;
  planned_claim_transaction_id: string;
  planned_claim_lease_token_id: string;
  planned_claim_cursor_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_scheduler_job_id: string;
  planned_runner_dispatch_id: string;
  planned_live_dispatch_receipt_id: string;
  planned_idempotency_key: string;
  planned_visibility_timeout_seconds: number;
  planned_lease_ttl_seconds: number;
  planned_heartbeat_interval_seconds: number;
  planned_max_attempts: number;
  planned_backoff_policy: "exponential_jitter";
  queue_claim_blockers: string[];
  required_queue_claim_invariants: string[];
  required_queue_claim_receipt_fields: string[];
  blocker_reason: "worker_queue_claim_unimplemented";
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  lease_retry_allowed: boolean;
  lease_policy_created: boolean;
  retry_policy_created: boolean;
  dead_letter_queue_created: boolean;
  worker_bootstrap_allowed: boolean;
  worker_bootstrap_created: boolean;
  worker_started: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  final_enablement_apply_allowed: boolean;
  final_enablement_allowed: boolean;
  live_dispatch_enabled: boolean;
  live_dispatch_ready: boolean;
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilRepositoryTransactionPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
  runner_dispatch_scheduler_plan_receipt: MidnightOilRunnerDispatchSchedulerPlanReceipt;
  runner_dispatch_worker_bootstrap_plan_receipt: MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt;
  scheduler_lease_retry_plan_receipt: MidnightOilSchedulerLeaseRetryPlanReceipt;
  worker_queue_claim_plan_receipt: MidnightOilWorkerQueueClaimPlanReceipt;
}

export interface MidnightOilRepositoryTransactionPlanReceipt {
  receipt_id: string;
  worker_queue_claim_plan_receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  live_dispatch_final_enablement_apply_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_repository_transaction_unimplemented";
  adapter_key: "repository_transaction";
  planned_repository_transaction_id: string;
  planned_transaction_scope: "worker_queue_claim_commit";
  planned_write_set_id: string;
  planned_lock_id: string;
  planned_commit_receipt_id: string;
  planned_rollback_receipt_id: string;
  planned_queue_claim_id: string;
  planned_claim_transaction_id: string;
  planned_claim_lease_token_id: string;
  planned_claim_cursor_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_live_dispatch_receipt_id: string;
  planned_idempotency_key: string;
  repository_transaction_blockers: string[];
  required_repository_transaction_invariants: string[];
  required_repository_transaction_receipt_fields: string[];
  blocker_reason: "repository_transaction_unimplemented";
  repository_transaction_allowed: boolean;
  repository_transaction_opened: boolean;
  repository_transaction_committed: boolean;
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  lease_retry_allowed: boolean;
  lease_policy_created: boolean;
  retry_policy_created: boolean;
  dead_letter_queue_created: boolean;
  worker_bootstrap_allowed: boolean;
  worker_bootstrap_created: boolean;
  worker_started: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  final_enablement_apply_allowed: boolean;
  final_enablement_allowed: boolean;
  live_dispatch_enabled: boolean;
  live_dispatch_ready: boolean;
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  rollback_receipt_created: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilRepositoryCommitRollbackPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
  runner_dispatch_scheduler_plan_receipt: MidnightOilRunnerDispatchSchedulerPlanReceipt;
  runner_dispatch_worker_bootstrap_plan_receipt: MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt;
  scheduler_lease_retry_plan_receipt: MidnightOilSchedulerLeaseRetryPlanReceipt;
  worker_queue_claim_plan_receipt: MidnightOilWorkerQueueClaimPlanReceipt;
  repository_transaction_plan_receipt: MidnightOilRepositoryTransactionPlanReceipt;
}

export interface MidnightOilRepositoryCommitRollbackPlanReceipt {
  receipt_id: string;
  repository_transaction_plan_receipt_id: string;
  worker_queue_claim_plan_receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  live_dispatch_final_enablement_apply_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_repository_commit_rollback_unimplemented";
  adapter_key: "repository_commit_rollback";
  planned_repository_transaction_id: string;
  planned_transaction_scope: "worker_queue_claim_commit";
  planned_write_set_id: string;
  planned_lock_id: string;
  planned_commit_receipt_id: string;
  planned_rollback_receipt_id: string;
  planned_commit_ledger_entry_id: string;
  planned_rollback_ledger_entry_id: string;
  planned_queue_claim_id: string;
  planned_claim_transaction_id: string;
  planned_claim_lease_token_id: string;
  planned_claim_cursor_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_live_dispatch_receipt_id: string;
  planned_idempotency_key: string;
  repository_commit_rollback_blockers: string[];
  required_repository_commit_rollback_invariants: string[];
  required_repository_commit_rollback_receipt_fields: string[];
  blocker_reason: "repository_commit_rollback_unimplemented";
  repository_commit_allowed: boolean;
  repository_rollback_allowed: boolean;
  commit_receipt_created: boolean;
  rollback_receipt_created: boolean;
  repository_transaction_allowed: boolean;
  repository_transaction_opened: boolean;
  repository_transaction_committed: boolean;
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  lease_retry_allowed: boolean;
  lease_policy_created: boolean;
  retry_policy_created: boolean;
  dead_letter_queue_created: boolean;
  worker_bootstrap_allowed: boolean;
  worker_bootstrap_created: boolean;
  worker_started: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  final_enablement_apply_allowed: boolean;
  final_enablement_allowed: boolean;
  live_dispatch_enabled: boolean;
  live_dispatch_ready: boolean;
  activation_readiness_allowed: boolean;
  activation_ready: boolean;
  transaction_opened: boolean;
  transaction_committed: boolean;
  setting_persisted: boolean;
  control_ledger_written: boolean;
  audit_log_written: boolean;
  operator_dispatch_allowed: boolean;
  operator_live_dispatch_enabled: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilWorkerDispatchLeaseHeartbeatPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
  runner_dispatch_scheduler_plan_receipt: MidnightOilRunnerDispatchSchedulerPlanReceipt;
  runner_dispatch_worker_bootstrap_plan_receipt: MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt;
  scheduler_lease_retry_plan_receipt: MidnightOilSchedulerLeaseRetryPlanReceipt;
  worker_queue_claim_plan_receipt: MidnightOilWorkerQueueClaimPlanReceipt;
  repository_transaction_plan_receipt: MidnightOilRepositoryTransactionPlanReceipt;
  repository_commit_rollback_plan_receipt: MidnightOilRepositoryCommitRollbackPlanReceipt;
}

export interface MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt {
  receipt_id: string;
  repository_commit_rollback_plan_receipt_id: string;
  repository_transaction_plan_receipt_id: string;
  worker_queue_claim_plan_receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_worker_dispatch_lease_heartbeat_unimplemented";
  adapter_key: "worker_dispatch_lease_heartbeat";
  planned_heartbeat_receipt_id: string;
  planned_lease_renewal_receipt_id: string;
  planned_lease_expiry_receipt_id: string;
  planned_heartbeat_ledger_entry_id: string;
  planned_queue_claim_id: string;
  planned_claim_lease_token_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_visibility_timeout_seconds: number;
  planned_lease_ttl_seconds: number;
  planned_heartbeat_interval_seconds: number;
  planned_max_missed_heartbeats: number;
  planned_idempotency_key: string;
  worker_dispatch_lease_heartbeat_blockers: string[];
  required_worker_dispatch_lease_heartbeat_invariants: string[];
  required_worker_dispatch_lease_heartbeat_receipt_fields: string[];
  blocker_reason: "worker_dispatch_lease_heartbeat_unimplemented";
  worker_lease_heartbeat_allowed: boolean;
  worker_lease_heartbeat_recorded: boolean;
  worker_lease_renewal_allowed: boolean;
  worker_lease_renewed: boolean;
  worker_lease_expiry_allowed: boolean;
  worker_lease_expired: boolean;
  worker_started: boolean;
  repository_commit_allowed: boolean;
  repository_rollback_allowed: boolean;
  commit_receipt_created: boolean;
  rollback_receipt_created: boolean;
  repository_transaction_allowed: boolean;
  repository_transaction_opened: boolean;
  repository_transaction_committed: boolean;
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilWorkerCancellationAbandonPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
  runner_dispatch_scheduler_plan_receipt: MidnightOilRunnerDispatchSchedulerPlanReceipt;
  runner_dispatch_worker_bootstrap_plan_receipt: MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt;
  scheduler_lease_retry_plan_receipt: MidnightOilSchedulerLeaseRetryPlanReceipt;
  worker_queue_claim_plan_receipt: MidnightOilWorkerQueueClaimPlanReceipt;
  repository_transaction_plan_receipt: MidnightOilRepositoryTransactionPlanReceipt;
  repository_commit_rollback_plan_receipt: MidnightOilRepositoryCommitRollbackPlanReceipt;
  worker_dispatch_lease_heartbeat_plan_receipt: MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt;
}

export interface MidnightOilWorkerCancellationAbandonPlanReceipt {
  receipt_id: string;
  worker_dispatch_lease_heartbeat_plan_receipt_id: string;
  repository_commit_rollback_plan_receipt_id: string;
  repository_transaction_plan_receipt_id: string;
  worker_queue_claim_plan_receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_worker_cancellation_abandon_unimplemented";
  adapter_key: "worker_cancellation_abandon";
  planned_cancellation_receipt_id: string;
  planned_abandon_receipt_id: string;
  planned_cancellation_ledger_entry_id: string;
  planned_abandon_ledger_entry_id: string;
  planned_queue_claim_id: string;
  planned_claim_lease_token_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_visibility_timeout_seconds: number;
  planned_lease_ttl_seconds: number;
  planned_abandon_after_missed_heartbeats: number;
  planned_idempotency_key: string;
  worker_cancellation_abandon_blockers: string[];
  required_worker_cancellation_abandon_invariants: string[];
  required_worker_cancellation_abandon_receipt_fields: string[];
  blocker_reason: "worker_cancellation_abandon_unimplemented";
  worker_cancellation_allowed: boolean;
  worker_cancelled: boolean;
  worker_abandon_allowed: boolean;
  worker_abandoned: boolean;
  worker_lease_heartbeat_allowed: boolean;
  worker_lease_heartbeat_recorded: boolean;
  worker_lease_renewal_allowed: boolean;
  worker_lease_renewed: boolean;
  worker_lease_expiry_allowed: boolean;
  worker_lease_expired: boolean;
  worker_started: boolean;
  repository_commit_allowed: boolean;
  repository_rollback_allowed: boolean;
  commit_receipt_created: boolean;
  rollback_receipt_created: boolean;
  repository_transaction_allowed: boolean;
  repository_transaction_opened: boolean;
  repository_transaction_committed: boolean;
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilWorkerCompletionFinalizationPlanRequest {
  launch_packet: MidnightOilLaunchPacket;
  approval_receipt: MidnightOilApprovalReceipt;
  runner_handoff: MidnightOilRunnerHandoff;
  runner_control_plan_receipt: MidnightOilRunnerControlPlanReceipt;
  budget_provider_adapter_plan_receipt: MidnightOilBudgetProviderAdapterPlanReceipt;
  provider_executor_adapter_plan_receipt: MidnightOilProviderExecutorAdapterPlanReceipt;
  retrieval_adapter_plan_receipt: MidnightOilRetrievalAdapterPlanReceipt;
  graph_adapter_plan_receipt: MidnightOilGraphAdapterPlanReceipt;
  final_artifact_adapter_plan_receipt: MidnightOilFinalArtifactAdapterPlanReceipt;
  operator_dispatch_adapter_plan_receipt: MidnightOilOperatorDispatchAdapterPlanReceipt;
  control_ledger_adapter_plan_receipt: MidnightOilControlLedgerAdapterPlanReceipt;
  control_ledger_persistence_plan_receipt: MidnightOilControlLedgerPersistencePlanReceipt;
  control_ledger_persistence_apply_plan_receipt: MidnightOilControlLedgerPersistenceApplyPlanReceipt;
  operator_dispatch_activation_readiness_plan_receipt: MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
  live_dispatch_final_enablement_plan_receipt: MidnightOilLiveDispatchFinalEnablementPlanReceipt;
  live_dispatch_final_enablement_apply_plan_receipt: MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
  runner_dispatch_scheduler_plan_receipt: MidnightOilRunnerDispatchSchedulerPlanReceipt;
  runner_dispatch_worker_bootstrap_plan_receipt: MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt;
  scheduler_lease_retry_plan_receipt: MidnightOilSchedulerLeaseRetryPlanReceipt;
  worker_queue_claim_plan_receipt: MidnightOilWorkerQueueClaimPlanReceipt;
  repository_transaction_plan_receipt: MidnightOilRepositoryTransactionPlanReceipt;
  repository_commit_rollback_plan_receipt: MidnightOilRepositoryCommitRollbackPlanReceipt;
  worker_dispatch_lease_heartbeat_plan_receipt: MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt;
  worker_cancellation_abandon_plan_receipt: MidnightOilWorkerCancellationAbandonPlanReceipt;
}

export interface MidnightOilWorkerCompletionFinalizationPlanReceipt {
  receipt_id: string;
  worker_cancellation_abandon_plan_receipt_id: string;
  worker_dispatch_lease_heartbeat_plan_receipt_id: string;
  repository_commit_rollback_plan_receipt_id: string;
  repository_transaction_plan_receipt_id: string;
  worker_queue_claim_plan_receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_worker_completion_finalization_unimplemented";
  adapter_key: "worker_completion_finalization";
  planned_completion_receipt_id: string;
  planned_finalization_receipt_id: string;
  planned_worker_result_manifest_id: string;
  planned_worker_output_bundle_id: string;
  planned_completion_ledger_entry_id: string;
  planned_finalization_ledger_entry_id: string;
  planned_queue_claim_id: string;
  planned_claim_lease_token_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  worker_completion_finalization_blockers: string[];
  required_worker_completion_finalization_invariants: string[];
  required_worker_completion_finalization_receipt_fields: string[];
  blocker_reason: "worker_completion_finalization_unimplemented";
  worker_completion_allowed: boolean;
  worker_completed: boolean;
  worker_finalization_allowed: boolean;
  worker_finalized: boolean;
  worker_result_manifest_created: boolean;
  worker_output_bundle_created: boolean;
  worker_cancellation_allowed: boolean;
  worker_cancelled: boolean;
  worker_abandon_allowed: boolean;
  worker_abandoned: boolean;
  worker_lease_heartbeat_allowed: boolean;
  worker_lease_heartbeat_recorded: boolean;
  worker_lease_renewal_allowed: boolean;
  worker_lease_renewed: boolean;
  worker_lease_expiry_allowed: boolean;
  worker_lease_expired: boolean;
  worker_started: boolean;
  repository_commit_allowed: boolean;
  repository_rollback_allowed: boolean;
  commit_receipt_created: boolean;
  rollback_receipt_created: boolean;
  repository_transaction_allowed: boolean;
  repository_transaction_opened: boolean;
  repository_transaction_committed: boolean;
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilWorkerOutputAggregationPlanRequest
  extends MidnightOilWorkerCompletionFinalizationPlanRequest {
  worker_completion_finalization_plan_receipt: MidnightOilWorkerCompletionFinalizationPlanReceipt;
}

export interface MidnightOilWorkerOutputAggregationPlanReceipt {
  receipt_id: string;
  worker_completion_finalization_plan_receipt_id: string;
  worker_cancellation_abandon_plan_receipt_id: string;
  worker_dispatch_lease_heartbeat_plan_receipt_id: string;
  repository_commit_rollback_plan_receipt_id: string;
  repository_transaction_plan_receipt_id: string;
  worker_queue_claim_plan_receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_worker_output_aggregation_unimplemented";
  adapter_key: "worker_output_aggregation";
  planned_worker_output_aggregation_receipt_id: string;
  planned_worker_output_index_id: string;
  planned_worker_output_manifest_id: string;
  planned_worker_output_summary_id: string;
  planned_worker_result_manifest_id: string;
  planned_worker_output_bundle_id: string;
  planned_output_aggregation_ledger_entry_id: string;
  planned_queue_claim_id: string;
  planned_claim_lease_token_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  worker_output_aggregation_blockers: string[];
  required_worker_output_aggregation_invariants: string[];
  required_worker_output_aggregation_receipt_fields: string[];
  blocker_reason: "worker_output_aggregation_unimplemented";
  worker_output_aggregation_allowed: boolean;
  worker_output_aggregated: boolean;
  worker_output_index_created: boolean;
  worker_output_manifest_created: boolean;
  worker_output_summary_created: boolean;
  worker_completion_allowed: boolean;
  worker_completed: boolean;
  worker_finalization_allowed: boolean;
  worker_finalized: boolean;
  worker_result_manifest_created: boolean;
  worker_output_bundle_created: boolean;
  worker_cancellation_allowed: boolean;
  worker_cancelled: boolean;
  worker_abandon_allowed: boolean;
  worker_abandoned: boolean;
  worker_lease_heartbeat_allowed: boolean;
  worker_lease_heartbeat_recorded: boolean;
  worker_lease_renewal_allowed: boolean;
  worker_lease_renewed: boolean;
  worker_lease_expiry_allowed: boolean;
  worker_lease_expired: boolean;
  worker_started: boolean;
  repository_commit_allowed: boolean;
  repository_rollback_allowed: boolean;
  commit_receipt_created: boolean;
  rollback_receipt_created: boolean;
  repository_transaction_allowed: boolean;
  repository_transaction_opened: boolean;
  repository_transaction_committed: boolean;
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilWorkerSynthesisHandoffPlanRequest
  extends MidnightOilWorkerOutputAggregationPlanRequest {
  worker_output_aggregation_plan_receipt: MidnightOilWorkerOutputAggregationPlanReceipt;
}

export interface MidnightOilWorkerSynthesisHandoffPlanReceipt {
  receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  worker_completion_finalization_plan_receipt_id: string;
  worker_cancellation_abandon_plan_receipt_id: string;
  worker_dispatch_lease_heartbeat_plan_receipt_id: string;
  repository_commit_rollback_plan_receipt_id: string;
  repository_transaction_plan_receipt_id: string;
  worker_queue_claim_plan_receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_worker_synthesis_handoff_unimplemented";
  adapter_key: "worker_synthesis_handoff";
  planned_synthesis_handoff_receipt_id: string;
  planned_synthesis_input_bundle_id: string;
  planned_synthesis_context_manifest_id: string;
  planned_synthesis_outline_id: string;
  planned_synthesis_handoff_ledger_entry_id: string;
  planned_worker_output_aggregation_receipt_id: string;
  planned_worker_output_index_id: string;
  planned_worker_output_manifest_id: string;
  planned_worker_output_summary_id: string;
  planned_worker_result_manifest_id: string;
  planned_worker_output_bundle_id: string;
  planned_queue_claim_id: string;
  planned_claim_lease_token_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  worker_synthesis_handoff_blockers: string[];
  required_worker_synthesis_handoff_invariants: string[];
  required_worker_synthesis_handoff_receipt_fields: string[];
  blocker_reason: "worker_synthesis_handoff_unimplemented";
  worker_synthesis_handoff_allowed: boolean;
  worker_synthesis_handoff_created: boolean;
  synthesis_input_bundle_created: boolean;
  synthesis_context_manifest_created: boolean;
  synthesis_outline_created: boolean;
  worker_output_aggregation_allowed: boolean;
  worker_output_aggregated: boolean;
  worker_output_index_created: boolean;
  worker_output_manifest_created: boolean;
  worker_output_summary_created: boolean;
  worker_completion_allowed: boolean;
  worker_completed: boolean;
  worker_finalization_allowed: boolean;
  worker_finalized: boolean;
  worker_result_manifest_created: boolean;
  worker_output_bundle_created: boolean;
  worker_cancellation_allowed: boolean;
  worker_cancelled: boolean;
  worker_abandon_allowed: boolean;
  worker_abandoned: boolean;
  worker_lease_heartbeat_allowed: boolean;
  worker_lease_heartbeat_recorded: boolean;
  worker_lease_renewal_allowed: boolean;
  worker_lease_renewed: boolean;
  worker_lease_expiry_allowed: boolean;
  worker_lease_expired: boolean;
  worker_started: boolean;
  repository_commit_allowed: boolean;
  repository_rollback_allowed: boolean;
  commit_receipt_created: boolean;
  rollback_receipt_created: boolean;
  repository_transaction_allowed: boolean;
  repository_transaction_opened: boolean;
  repository_transaction_committed: boolean;
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilSynthesisBundleAssemblyPlanRequest
  extends MidnightOilWorkerSynthesisHandoffPlanRequest {
  worker_synthesis_handoff_plan_receipt: MidnightOilWorkerSynthesisHandoffPlanReceipt;
}

export interface MidnightOilSynthesisBundleAssemblyPlanReceipt {
  receipt_id: string;
  worker_synthesis_handoff_plan_receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  worker_completion_finalization_plan_receipt_id: string;
  worker_cancellation_abandon_plan_receipt_id: string;
  worker_dispatch_lease_heartbeat_plan_receipt_id: string;
  repository_commit_rollback_plan_receipt_id: string;
  repository_transaction_plan_receipt_id: string;
  worker_queue_claim_plan_receipt_id: string;
  scheduler_lease_retry_plan_receipt_id: string;
  runner_dispatch_worker_bootstrap_plan_receipt_id: string;
  runner_dispatch_scheduler_plan_receipt_id: string;
  runner_control_plan_receipt_id: string;
  runner_readiness_receipt_id: string;
  runner_handoff_id: string;
  approval_receipt_id: string;
  launch_packet_id: string;
  run_id: string;
  status: "blocked_synthesis_bundle_assembly_unimplemented";
  adapter_key: "synthesis_bundle_assembly";
  planned_synthesis_bundle_assembly_receipt_id: string;
  planned_synthesis_bundle_id: string;
  planned_synthesis_source_packet_id: string;
  planned_synthesis_evidence_map_id: string;
  planned_synthesis_composition_plan_id: string;
  planned_synthesis_quality_gate_id: string;
  planned_synthesis_handoff_receipt_id: string;
  planned_synthesis_input_bundle_id: string;
  planned_synthesis_context_manifest_id: string;
  planned_synthesis_outline_id: string;
  planned_synthesis_handoff_ledger_entry_id: string;
  planned_worker_output_aggregation_receipt_id: string;
  planned_worker_output_index_id: string;
  planned_worker_output_manifest_id: string;
  planned_worker_output_summary_id: string;
  planned_worker_result_manifest_id: string;
  planned_worker_output_bundle_id: string;
  planned_queue_claim_id: string;
  planned_claim_lease_token_id: string;
  planned_queue_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  synthesis_bundle_assembly_blockers: string[];
  required_synthesis_bundle_assembly_invariants: string[];
  required_synthesis_bundle_assembly_receipt_fields: string[];
  blocker_reason: "synthesis_bundle_assembly_unimplemented";
  synthesis_bundle_assembly_allowed: boolean;
  synthesis_bundle_assembled: boolean;
  synthesis_source_packet_created: boolean;
  synthesis_evidence_map_created: boolean;
  synthesis_composition_plan_created: boolean;
  synthesis_quality_gate_created: boolean;
  worker_synthesis_handoff_allowed: boolean;
  worker_synthesis_handoff_created: boolean;
  synthesis_input_bundle_created: boolean;
  synthesis_context_manifest_created: boolean;
  synthesis_outline_created: boolean;
  worker_output_aggregation_allowed: boolean;
  worker_output_aggregated: boolean;
  worker_output_index_created: boolean;
  worker_output_manifest_created: boolean;
  worker_output_summary_created: boolean;
  worker_completion_allowed: boolean;
  worker_completed: boolean;
  worker_finalization_allowed: boolean;
  worker_finalized: boolean;
  worker_result_manifest_created: boolean;
  worker_output_bundle_created: boolean;
  worker_cancellation_allowed: boolean;
  worker_cancelled: boolean;
  worker_abandon_allowed: boolean;
  worker_abandoned: boolean;
  worker_lease_heartbeat_allowed: boolean;
  worker_lease_heartbeat_recorded: boolean;
  worker_lease_renewal_allowed: boolean;
  worker_lease_renewed: boolean;
  worker_lease_expiry_allowed: boolean;
  worker_lease_expired: boolean;
  worker_started: boolean;
  repository_commit_allowed: boolean;
  repository_rollback_allowed: boolean;
  commit_receipt_created: boolean;
  rollback_receipt_created: boolean;
  repository_transaction_allowed: boolean;
  repository_transaction_opened: boolean;
  repository_transaction_committed: boolean;
  queue_claim_allowed: boolean;
  queue_claim_created: boolean;
  claim_transaction_opened: boolean;
  claim_transaction_committed: boolean;
  scheduler_allowed: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  live_run_allowed: boolean;
  dispatch_allowed: boolean;
  dispatch_performed: boolean;
  budget_reservation_allowed: boolean;
  budget_reserved: boolean;
  provider_execution_allowed: boolean;
  provider_calls_made: boolean;
  retrieval_allowed: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutation_allowed: boolean;
  graph_mutated: boolean;
  final_artifact_allowed: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalSynthesisDraftPlanRequest
  extends MidnightOilSynthesisBundleAssemblyPlanRequest {
  synthesis_bundle_assembly_plan_receipt: MidnightOilSynthesisBundleAssemblyPlanReceipt;
}

export interface MidnightOilFinalSynthesisDraftPlanReceipt {
  receipt_id: string;
  synthesis_bundle_assembly_plan_receipt_id: string;
  worker_synthesis_handoff_plan_receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_final_synthesis_draft_unimplemented";
  adapter_key: "final_synthesis_draft";
  planned_final_synthesis_draft_receipt_id: string;
  planned_final_synthesis_draft_id: string;
  planned_final_synthesis_outline_id: string;
  planned_final_synthesis_claim_map_id: string;
  planned_final_synthesis_citation_map_id: string;
  planned_final_synthesis_gap_list_id: string;
  planned_final_synthesis_quality_report_id: string;
  planned_synthesis_bundle_assembly_receipt_id: string;
  planned_synthesis_bundle_id: string;
  planned_synthesis_source_packet_id: string;
  planned_synthesis_evidence_map_id: string;
  planned_synthesis_composition_plan_id: string;
  planned_synthesis_quality_gate_id: string;
  planned_synthesis_input_bundle_id: string;
  planned_synthesis_context_manifest_id: string;
  planned_synthesis_outline_id: string;
  planned_worker_output_index_id: string;
  planned_worker_output_manifest_id: string;
  planned_worker_output_summary_id: string;
  planned_worker_result_manifest_id: string;
  planned_worker_output_bundle_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  final_synthesis_draft_blockers: string[];
  required_final_synthesis_draft_invariants: string[];
  required_final_synthesis_draft_receipt_fields: string[];
  blocker_reason: "final_synthesis_draft_unimplemented";
  final_synthesis_draft_allowed: boolean;
  final_synthesis_draft_created: boolean;
  final_synthesis_outline_created: boolean;
  final_synthesis_claim_map_created: boolean;
  final_synthesis_citation_map_created: boolean;
  final_synthesis_gap_list_created: boolean;
  final_synthesis_quality_report_created: boolean;
  synthesis_bundle_assembly_allowed: boolean;
  synthesis_bundle_assembled: boolean;
  synthesis_source_packet_created: boolean;
  synthesis_evidence_map_created: boolean;
  synthesis_composition_plan_created: boolean;
  synthesis_quality_gate_created: boolean;
  worker_synthesis_handoff_created: boolean;
  synthesis_input_bundle_created: boolean;
  synthesis_context_manifest_created: boolean;
  synthesis_outline_created: boolean;
  worker_output_aggregated: boolean;
  worker_started: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalHtmlArtifactAssemblyPlanRequest
  extends MidnightOilFinalSynthesisDraftPlanRequest {
  final_synthesis_draft_plan_receipt: MidnightOilFinalSynthesisDraftPlanReceipt;
}

export interface MidnightOilFinalHtmlArtifactAssemblyPlanReceipt {
  receipt_id: string;
  final_synthesis_draft_plan_receipt_id: string;
  synthesis_bundle_assembly_plan_receipt_id: string;
  worker_synthesis_handoff_plan_receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_final_html_artifact_assembly_unimplemented";
  adapter_key: "final_html_artifact_assembly";
  planned_final_html_artifact_assembly_receipt_id: string;
  planned_final_html_artifact_id: string;
  planned_final_html_asset_id: string;
  planned_final_html_document_id: string;
  planned_final_html_twin_notes_document_id: string;
  planned_final_html_citation_index_id: string;
  planned_final_html_export_manifest_id: string;
  planned_final_synthesis_draft_receipt_id: string;
  planned_final_synthesis_draft_id: string;
  planned_final_synthesis_outline_id: string;
  planned_final_synthesis_claim_map_id: string;
  planned_final_synthesis_citation_map_id: string;
  planned_final_synthesis_gap_list_id: string;
  planned_final_synthesis_quality_report_id: string;
  planned_synthesis_bundle_id: string;
  planned_synthesis_source_packet_id: string;
  planned_synthesis_evidence_map_id: string;
  planned_synthesis_composition_plan_id: string;
  planned_synthesis_quality_gate_id: string;
  planned_worker_id: string;
  planned_worker_lease_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  final_html_artifact_assembly_blockers: string[];
  required_final_html_artifact_assembly_invariants: string[];
  required_final_html_artifact_assembly_receipt_fields: string[];
  blocker_reason: "final_html_artifact_assembly_unimplemented";
  final_html_artifact_assembly_allowed: boolean;
  final_html_artifact_assembled: boolean;
  final_html_asset_created: boolean;
  final_html_document_created: boolean;
  final_html_twin_notes_document_created: boolean;
  final_html_citation_index_created: boolean;
  final_html_export_manifest_created: boolean;
  final_synthesis_draft_created: boolean;
  final_synthesis_outline_created: boolean;
  final_synthesis_claim_map_created: boolean;
  final_synthesis_citation_map_created: boolean;
  final_synthesis_gap_list_created: boolean;
  final_synthesis_quality_report_created: boolean;
  synthesis_bundle_assembled: boolean;
  worker_output_aggregated: boolean;
  worker_started: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalArtifactPersistencePlanRequest
  extends MidnightOilFinalHtmlArtifactAssemblyPlanRequest {
  final_html_artifact_assembly_plan_receipt: MidnightOilFinalHtmlArtifactAssemblyPlanReceipt;
}

export interface MidnightOilFinalArtifactPersistencePlanReceipt {
  receipt_id: string;
  final_html_artifact_assembly_plan_receipt_id: string;
  final_synthesis_draft_plan_receipt_id: string;
  synthesis_bundle_assembly_plan_receipt_id: string;
  worker_synthesis_handoff_plan_receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_final_artifact_persistence_unimplemented";
  adapter_key: "final_artifact_persistence";
  planned_final_artifact_persistence_receipt_id: string;
  planned_persisted_final_artifact_id: string;
  planned_information_asset_id: string;
  planned_hosted_html_asset_id: string;
  planned_account_asset_binding_id: string;
  planned_twin_notes_binding_id: string;
  planned_citation_index_binding_id: string;
  planned_graph_node_id: string;
  planned_graph_edge_set_id: string;
  planned_artifact_ledger_entry_id: string;
  planned_final_html_artifact_id: string;
  planned_final_html_asset_id: string;
  planned_final_html_document_id: string;
  planned_final_html_twin_notes_document_id: string;
  planned_final_html_citation_index_id: string;
  planned_final_html_export_manifest_id: string;
  planned_final_synthesis_draft_id: string;
  planned_synthesis_bundle_id: string;
  planned_synthesis_source_packet_id: string;
  planned_synthesis_evidence_map_id: string;
  planned_worker_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  final_artifact_persistence_blockers: string[];
  required_final_artifact_persistence_invariants: string[];
  required_final_artifact_persistence_receipt_fields: string[];
  blocker_reason: "final_artifact_persistence_unimplemented";
  final_artifact_persistence_allowed: boolean;
  final_artifact_persisted: boolean;
  information_asset_created: boolean;
  hosted_html_asset_created: boolean;
  account_asset_binding_created: boolean;
  twin_notes_binding_created: boolean;
  citation_index_binding_created: boolean;
  artifact_ledger_entry_created: boolean;
  graph_node_created: boolean;
  graph_edge_set_created: boolean;
  final_html_artifact_assembled: boolean;
  final_html_document_created: boolean;
  final_html_twin_notes_document_created: boolean;
  final_html_citation_index_created: boolean;
  final_synthesis_draft_created: boolean;
  synthesis_bundle_assembled: boolean;
  worker_output_aggregated: boolean;
  worker_started: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalArtifactGraphCommitPlanRequest
  extends MidnightOilFinalArtifactPersistencePlanRequest {
  final_artifact_persistence_plan_receipt: MidnightOilFinalArtifactPersistencePlanReceipt;
}

export interface MidnightOilFinalArtifactGraphCommitPlanReceipt {
  receipt_id: string;
  final_artifact_persistence_plan_receipt_id: string;
  final_html_artifact_assembly_plan_receipt_id: string;
  final_synthesis_draft_plan_receipt_id: string;
  synthesis_bundle_assembly_plan_receipt_id: string;
  worker_synthesis_handoff_plan_receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_final_artifact_graph_commit_unimplemented";
  adapter_key: "final_artifact_graph_commit";
  planned_final_artifact_graph_commit_receipt_id: string;
  planned_graph_commit_id: string;
  planned_graph_transaction_id: string;
  planned_graph_node_id: string;
  planned_graph_edge_set_id: string;
  planned_graph_snapshot_id: string;
  planned_graph_lineage_index_id: string;
  planned_information_asset_id: string;
  planned_hosted_html_asset_id: string;
  planned_artifact_ledger_entry_id: string;
  planned_final_html_artifact_id: string;
  planned_final_html_document_id: string;
  planned_final_synthesis_draft_id: string;
  planned_synthesis_bundle_id: string;
  planned_synthesis_source_packet_id: string;
  planned_synthesis_evidence_map_id: string;
  planned_worker_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  final_artifact_graph_commit_blockers: string[];
  required_final_artifact_graph_commit_invariants: string[];
  required_final_artifact_graph_commit_receipt_fields: string[];
  blocker_reason: "final_artifact_graph_commit_unimplemented";
  final_artifact_graph_commit_allowed: boolean;
  graph_commit_created: boolean;
  graph_transaction_created: boolean;
  graph_node_committed: boolean;
  graph_edge_set_committed: boolean;
  graph_snapshot_created: boolean;
  graph_lineage_index_created: boolean;
  final_artifact_persistence_allowed: boolean;
  final_artifact_persisted: boolean;
  information_asset_created: boolean;
  hosted_html_asset_created: boolean;
  artifact_ledger_entry_created: boolean;
  graph_node_created: boolean;
  graph_edge_set_created: boolean;
  final_html_artifact_assembled: boolean;
  final_synthesis_draft_created: boolean;
  synthesis_bundle_assembled: boolean;
  worker_output_aggregated: boolean;
  worker_started: boolean;
  scheduler_job_created: boolean;
  runner_dispatch_enqueued: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalArtifactPublishPlanRequest
  extends MidnightOilFinalArtifactGraphCommitPlanRequest {
  final_artifact_graph_commit_plan_receipt: MidnightOilFinalArtifactGraphCommitPlanReceipt;
}

export interface MidnightOilFinalArtifactPublishPlanReceipt {
  receipt_id: string;
  final_artifact_graph_commit_plan_receipt_id: string;
  final_artifact_persistence_plan_receipt_id: string;
  final_html_artifact_assembly_plan_receipt_id: string;
  final_synthesis_draft_plan_receipt_id: string;
  synthesis_bundle_assembly_plan_receipt_id: string;
  worker_synthesis_handoff_plan_receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_final_artifact_publish_unimplemented";
  adapter_key: "final_artifact_publish";
  planned_final_artifact_publish_receipt_id: string;
  planned_publish_transaction_id: string;
  planned_published_information_asset_id: string;
  planned_account_visible_asset_id: string;
  planned_reading_workspace_entry_id: string;
  planned_twin_notes_workspace_entry_id: string;
  planned_search_index_entry_id: string;
  planned_share_policy_id: string;
  planned_private_read_url_id: string;
  planned_operator_notification_id: string;
  planned_graph_commit_id: string;
  planned_graph_snapshot_id: string;
  planned_graph_lineage_index_id: string;
  planned_information_asset_id: string;
  planned_hosted_html_asset_id: string;
  planned_final_html_artifact_id: string;
  planned_final_html_document_id: string;
  planned_synthesis_source_packet_id: string;
  planned_synthesis_evidence_map_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  final_artifact_publish_blockers: string[];
  required_final_artifact_publish_invariants: string[];
  required_final_artifact_publish_receipt_fields: string[];
  blocker_reason: "final_artifact_publish_unimplemented";
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  twin_notes_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  share_policy_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  final_artifact_graph_commit_allowed: boolean;
  graph_commit_created: boolean;
  graph_transaction_created: boolean;
  graph_node_committed: boolean;
  graph_edge_set_committed: boolean;
  graph_snapshot_created: boolean;
  graph_lineage_index_created: boolean;
  final_artifact_persisted: boolean;
  information_asset_created: boolean;
  hosted_html_asset_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalArtifactCompletionFinalizationPlanRequest
  extends MidnightOilFinalArtifactPublishPlanRequest {
  final_artifact_publish_plan_receipt: MidnightOilFinalArtifactPublishPlanReceipt;
}

export interface MidnightOilFinalArtifactCompletionFinalizationPlanReceipt {
  receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  final_artifact_graph_commit_plan_receipt_id: string;
  final_artifact_persistence_plan_receipt_id: string;
  final_html_artifact_assembly_plan_receipt_id: string;
  final_synthesis_draft_plan_receipt_id: string;
  synthesis_bundle_assembly_plan_receipt_id: string;
  worker_synthesis_handoff_plan_receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_final_artifact_completion_finalization_unimplemented";
  adapter_key: "final_artifact_completion_finalization";
  planned_final_artifact_completion_receipt_id: string;
  planned_final_artifact_finalization_receipt_id: string;
  planned_completion_record_id: string;
  planned_finalization_transaction_id: string;
  planned_artifact_archive_manifest_id: string;
  planned_operator_handoff_summary_id: string;
  planned_delivery_status_id: string;
  planned_quality_attestation_id: string;
  planned_completion_audit_entry_id: string;
  planned_publish_transaction_id: string;
  planned_account_visible_asset_id: string;
  planned_reading_workspace_entry_id: string;
  planned_search_index_entry_id: string;
  planned_private_read_url_id: string;
  planned_graph_commit_id: string;
  planned_graph_snapshot_id: string;
  planned_information_asset_id: string;
  planned_hosted_html_asset_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  final_artifact_completion_finalization_blockers: string[];
  required_final_artifact_completion_finalization_invariants: string[];
  required_final_artifact_completion_finalization_receipt_fields: string[];
  blocker_reason: "final_artifact_completion_finalization_unimplemented";
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalRunClosurePlanRequest
  extends MidnightOilFinalArtifactCompletionFinalizationPlanRequest {
  final_artifact_completion_finalization_plan_receipt: MidnightOilFinalArtifactCompletionFinalizationPlanReceipt;
}

export interface MidnightOilFinalRunClosurePlanReceipt {
  receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  final_artifact_graph_commit_plan_receipt_id: string;
  final_artifact_persistence_plan_receipt_id: string;
  final_html_artifact_assembly_plan_receipt_id: string;
  final_synthesis_draft_plan_receipt_id: string;
  synthesis_bundle_assembly_plan_receipt_id: string;
  worker_synthesis_handoff_plan_receipt_id: string;
  worker_output_aggregation_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_final_run_closure_unimplemented";
  adapter_key: "final_run_closure";
  planned_final_run_closure_receipt_id: string;
  planned_run_closeout_record_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_delivery_notification_id: string;
  planned_workspace_delivery_card_id: string;
  planned_run_retention_manifest_id: string;
  planned_billing_reconciliation_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_final_artifact_completion_receipt_id: string;
  planned_final_artifact_finalization_receipt_id: string;
  planned_completion_record_id: string;
  planned_artifact_archive_manifest_id: string;
  planned_operator_handoff_summary_id: string;
  planned_delivery_status_id: string;
  planned_quality_attestation_id: string;
  planned_completion_audit_entry_id: string;
  planned_account_visible_asset_id: string;
  planned_reading_workspace_entry_id: string;
  planned_search_index_entry_id: string;
  planned_private_read_url_id: string;
  planned_graph_commit_id: string;
  planned_graph_snapshot_id: string;
  planned_information_asset_id: string;
  planned_hosted_html_asset_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  final_run_closure_blockers: string[];
  required_final_run_closure_invariants: string[];
  required_final_run_closure_receipt_fields: string[];
  blocker_reason: "final_run_closure_unimplemented";
  final_run_closure_allowed: boolean;
  run_closeout_record_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  delivery_notification_created: boolean;
  workspace_delivery_card_created: boolean;
  run_retention_manifest_created: boolean;
  billing_reconciliation_created: boolean;
  model_usage_rollup_created: boolean;
  source_lineage_archive_created: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorNotificationDeliveryReadinessPlanRequest
  extends MidnightOilFinalRunClosurePlanRequest {
  final_run_closure_plan_receipt: MidnightOilFinalRunClosurePlanReceipt;
}

export interface MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt {
  receipt_id: string;
  final_run_closure_plan_receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_operator_notification_delivery_readiness_unimplemented";
  adapter_key: "operator_notification_delivery_readiness";
  planned_operator_notification_delivery_readiness_receipt_id: string;
  planned_operator_notification_dispatch_id: string;
  planned_operator_notification_payload_id: string;
  planned_operator_delivery_channel_policy_id: string;
  planned_operator_notification_template_id: string;
  planned_operator_notification_audit_entry_id: string;
  planned_workspace_delivery_card_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_delivery_notification_id: string;
  planned_run_closeout_record_id: string;
  planned_final_run_closure_receipt_id: string;
  planned_account_visible_asset_id: string;
  planned_private_read_url_id: string;
  planned_reading_workspace_entry_id: string;
  planned_hosted_html_asset_id: string;
  planned_quality_attestation_id: string;
  planned_completion_audit_entry_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  operator_notification_delivery_readiness_blockers: string[];
  required_operator_notification_delivery_readiness_invariants: string[];
  required_operator_notification_delivery_readiness_receipt_fields: string[];
  blocker_reason: "operator_notification_delivery_readiness_unimplemented";
  operator_notification_delivery_readiness_allowed: boolean;
  operator_notification_dispatch_created: boolean;
  operator_notification_payload_created: boolean;
  operator_delivery_channel_policy_created: boolean;
  operator_notification_template_created: boolean;
  operator_notification_audit_entry_created: boolean;
  delivery_notification_created: boolean;
  workspace_delivery_card_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  run_closeout_record_created: boolean;
  final_run_closure_allowed: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorNotificationDeliveryApplyPlanRequest
  extends MidnightOilOperatorNotificationDeliveryReadinessPlanRequest {
  operator_notification_delivery_readiness_plan_receipt: MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt;
}

export interface MidnightOilOperatorNotificationDeliveryApplyPlanReceipt {
  receipt_id: string;
  operator_notification_delivery_readiness_plan_receipt_id: string;
  final_run_closure_plan_receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_operator_notification_delivery_apply_unimplemented";
  adapter_key: "operator_notification_delivery_apply";
  planned_operator_notification_delivery_apply_receipt_id: string;
  planned_operator_notification_delivery_transaction_id: string;
  planned_operator_notification_dispatch_id: string;
  planned_operator_notification_payload_id: string;
  planned_operator_delivery_channel_policy_id: string;
  planned_operator_notification_template_id: string;
  planned_operator_notification_audit_entry_id: string;
  planned_operator_notification_delivery_attempt_id: string;
  planned_operator_notification_delivery_result_id: string;
  planned_operator_notification_delivery_status_id: string;
  planned_operator_notification_retry_policy_id: string;
  planned_operator_notification_dead_letter_id: string;
  planned_workspace_delivery_card_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_delivery_notification_id: string;
  planned_run_closeout_record_id: string;
  planned_final_run_closure_receipt_id: string;
  planned_account_visible_asset_id: string;
  planned_private_read_url_id: string;
  planned_reading_workspace_entry_id: string;
  planned_hosted_html_asset_id: string;
  planned_quality_attestation_id: string;
  planned_completion_audit_entry_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  operator_notification_delivery_apply_blockers: string[];
  required_operator_notification_delivery_apply_invariants: string[];
  required_operator_notification_delivery_apply_receipt_fields: string[];
  blocker_reason: "operator_notification_delivery_apply_unimplemented";
  operator_notification_delivery_apply_allowed: boolean;
  operator_notification_delivery_transaction_created: boolean;
  operator_notification_dispatch_created: boolean;
  operator_notification_payload_created: boolean;
  operator_delivery_channel_policy_created: boolean;
  operator_notification_template_created: boolean;
  operator_notification_audit_entry_created: boolean;
  operator_notification_delivery_attempt_created: boolean;
  operator_notification_delivery_result_created: boolean;
  operator_notification_delivery_status_created: boolean;
  operator_notification_retry_policy_created: boolean;
  operator_notification_dead_letter_created: boolean;
  operator_notification_delivery_readiness_allowed: boolean;
  delivery_notification_created: boolean;
  workspace_delivery_card_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  run_closeout_record_created: boolean;
  final_run_closure_allowed: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorNotificationDeliveryResultReconciliationPlanRequest
  extends MidnightOilOperatorNotificationDeliveryApplyPlanRequest {
  operator_notification_delivery_apply_plan_receipt: MidnightOilOperatorNotificationDeliveryApplyPlanReceipt;
}

export interface MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt {
  receipt_id: string;
  operator_notification_delivery_apply_plan_receipt_id: string;
  operator_notification_delivery_readiness_plan_receipt_id: string;
  final_run_closure_plan_receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_operator_notification_delivery_result_reconciliation_unimplemented";
  adapter_key: "operator_notification_delivery_result_reconciliation";
  planned_operator_notification_delivery_result_reconciliation_receipt_id: string;
  planned_operator_notification_delivery_apply_receipt_id: string;
  planned_operator_notification_delivery_transaction_id: string;
  planned_operator_notification_dispatch_id: string;
  planned_operator_notification_payload_id: string;
  planned_operator_notification_delivery_attempt_id: string;
  planned_operator_notification_delivery_result_id: string;
  planned_operator_notification_delivery_status_id: string;
  planned_operator_notification_delivery_outcome_record_id: string;
  planned_operator_notification_delivery_reconciliation_entry_id: string;
  planned_operator_notification_delivery_retry_policy_id: string;
  planned_operator_notification_delivery_retry_decision_id: string;
  planned_operator_notification_dead_letter_id: string;
  planned_operator_notification_dead_letter_entry_id: string;
  planned_operator_notification_audit_entry_id: string;
  planned_workspace_delivery_card_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_delivery_notification_id: string;
  planned_run_closeout_record_id: string;
  planned_final_run_closure_receipt_id: string;
  planned_account_visible_asset_id: string;
  planned_private_read_url_id: string;
  planned_reading_workspace_entry_id: string;
  planned_hosted_html_asset_id: string;
  planned_quality_attestation_id: string;
  planned_completion_audit_entry_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  operator_notification_delivery_result_reconciliation_blockers: string[];
  required_operator_notification_delivery_result_reconciliation_invariants: string[];
  required_operator_notification_delivery_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_notification_delivery_result_reconciliation_unimplemented";
  operator_notification_delivery_result_reconciliation_allowed: boolean;
  operator_notification_delivery_outcome_record_created: boolean;
  operator_notification_delivery_reconciliation_entry_created: boolean;
  operator_notification_delivery_retry_decision_created: boolean;
  operator_notification_dead_letter_entry_created: boolean;
  operator_notification_delivery_apply_allowed: boolean;
  operator_notification_delivery_transaction_created: boolean;
  operator_notification_dispatch_created: boolean;
  operator_notification_payload_created: boolean;
  operator_delivery_channel_policy_created: boolean;
  operator_notification_template_created: boolean;
  operator_notification_audit_entry_created: boolean;
  operator_notification_delivery_attempt_created: boolean;
  operator_notification_delivery_result_created: boolean;
  operator_notification_delivery_status_created: boolean;
  operator_notification_retry_policy_created: boolean;
  operator_notification_dead_letter_created: boolean;
  operator_notification_delivery_readiness_allowed: boolean;
  delivery_notification_created: boolean;
  workspace_delivery_card_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  run_closeout_record_created: boolean;
  final_run_closure_allowed: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorDeliveryLedgerReconciliationPlanRequest
  extends MidnightOilOperatorNotificationDeliveryResultReconciliationPlanRequest {
  operator_notification_delivery_result_reconciliation_plan_receipt: MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorDeliveryLedgerReconciliationPlanReceipt {
  receipt_id: string;
  operator_notification_delivery_result_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_apply_plan_receipt_id: string;
  operator_notification_delivery_readiness_plan_receipt_id: string;
  final_run_closure_plan_receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_operator_delivery_ledger_reconciliation_unimplemented";
  adapter_key: "operator_delivery_ledger_reconciliation";
  planned_operator_delivery_ledger_reconciliation_receipt_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_operator_delivery_ledger_result_entry_id: string;
  planned_operator_delivery_ledger_status_entry_id: string;
  planned_operator_delivery_ledger_retry_entry_id: string;
  planned_operator_delivery_ledger_dead_letter_entry_id: string;
  planned_operator_notification_delivery_result_reconciliation_receipt_id: string;
  planned_operator_notification_delivery_outcome_record_id: string;
  planned_operator_notification_delivery_reconciliation_entry_id: string;
  planned_operator_notification_delivery_retry_decision_id: string;
  planned_operator_notification_dead_letter_entry_id: string;
  planned_operator_notification_delivery_apply_receipt_id: string;
  planned_operator_notification_delivery_transaction_id: string;
  planned_operator_notification_dispatch_id: string;
  planned_operator_notification_payload_id: string;
  planned_operator_notification_delivery_attempt_id: string;
  planned_operator_notification_delivery_result_id: string;
  planned_operator_notification_delivery_status_id: string;
  planned_operator_notification_delivery_retry_policy_id: string;
  planned_operator_notification_dead_letter_id: string;
  planned_operator_notification_audit_entry_id: string;
  planned_workspace_delivery_card_id: string;
  planned_delivery_notification_id: string;
  planned_run_closeout_record_id: string;
  planned_final_run_closure_receipt_id: string;
  planned_account_visible_asset_id: string;
  planned_private_read_url_id: string;
  planned_reading_workspace_entry_id: string;
  planned_hosted_html_asset_id: string;
  planned_quality_attestation_id: string;
  planned_completion_audit_entry_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_runner_dispatch_id: string;
  planned_idempotency_key: string;
  operator_delivery_ledger_reconciliation_blockers: string[];
  required_operator_delivery_ledger_reconciliation_invariants: string[];
  required_operator_delivery_ledger_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_delivery_ledger_reconciliation_unimplemented";
  operator_delivery_ledger_reconciliation_allowed: boolean;
  operator_delivery_ledger_result_entry_created: boolean;
  operator_delivery_ledger_status_entry_created: boolean;
  operator_delivery_ledger_retry_entry_created: boolean;
  operator_delivery_ledger_dead_letter_entry_created: boolean;
  operator_notification_delivery_result_reconciliation_allowed: boolean;
  operator_notification_delivery_outcome_record_created: boolean;
  operator_notification_delivery_reconciliation_entry_created: boolean;
  operator_notification_delivery_retry_decision_created: boolean;
  operator_notification_dead_letter_entry_created: boolean;
  operator_notification_delivery_apply_allowed: boolean;
  operator_notification_delivery_transaction_created: boolean;
  operator_notification_dispatch_created: boolean;
  operator_notification_payload_created: boolean;
  operator_delivery_channel_policy_created: boolean;
  operator_notification_template_created: boolean;
  operator_notification_audit_entry_created: boolean;
  operator_notification_delivery_attempt_created: boolean;
  operator_notification_delivery_result_created: boolean;
  operator_notification_delivery_status_created: boolean;
  operator_notification_retry_policy_created: boolean;
  operator_notification_dead_letter_created: boolean;
  operator_notification_delivery_readiness_allowed: boolean;
  delivery_notification_created: boolean;
  workspace_delivery_card_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  run_closeout_record_created: boolean;
  final_run_closure_allowed: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilWorkspaceDeliveryCardReconciliationPlanRequest
  extends MidnightOilOperatorDeliveryLedgerReconciliationPlanRequest {
  operator_delivery_ledger_reconciliation_plan_receipt: MidnightOilOperatorDeliveryLedgerReconciliationPlanReceipt;
}

export interface MidnightOilWorkspaceDeliveryCardReconciliationPlanReceipt {
  receipt_id: string;
  operator_delivery_ledger_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_result_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_apply_plan_receipt_id: string;
  operator_notification_delivery_readiness_plan_receipt_id: string;
  final_run_closure_plan_receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_workspace_delivery_card_reconciliation_unimplemented";
  adapter_key: "workspace_delivery_card_reconciliation";
  planned_workspace_delivery_card_reconciliation_receipt_id: string;
  planned_workspace_delivery_card_id: string;
  planned_workspace_delivery_card_result_entry_id: string;
  planned_workspace_delivery_card_status_entry_id: string;
  planned_workspace_delivery_card_notification_entry_id: string;
  planned_workspace_delivery_card_replay_guard_id: string;
  planned_operator_delivery_ledger_reconciliation_receipt_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_operator_delivery_ledger_result_entry_id: string;
  planned_operator_delivery_ledger_status_entry_id: string;
  planned_operator_delivery_ledger_retry_entry_id: string;
  planned_operator_delivery_ledger_dead_letter_entry_id: string;
  planned_operator_notification_delivery_outcome_record_id: string;
  planned_operator_notification_delivery_reconciliation_entry_id: string;
  planned_operator_notification_delivery_retry_decision_id: string;
  planned_operator_notification_dead_letter_entry_id: string;
  planned_operator_notification_delivery_result_id: string;
  planned_operator_notification_delivery_status_id: string;
  planned_delivery_notification_id: string;
  planned_private_read_url_id: string;
  planned_reading_workspace_entry_id: string;
  planned_hosted_html_asset_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_idempotency_key: string;
  workspace_delivery_card_reconciliation_blockers: string[];
  required_workspace_delivery_card_reconciliation_invariants: string[];
  required_workspace_delivery_card_reconciliation_receipt_fields: string[];
  blocker_reason: "workspace_delivery_card_reconciliation_unimplemented";
  workspace_delivery_card_reconciliation_allowed: boolean;
  workspace_delivery_card_result_entry_created: boolean;
  workspace_delivery_card_status_entry_created: boolean;
  workspace_delivery_card_notification_entry_created: boolean;
  workspace_delivery_card_created: boolean;
  operator_delivery_ledger_reconciliation_allowed: boolean;
  operator_delivery_ledger_result_entry_created: boolean;
  operator_delivery_ledger_status_entry_created: boolean;
  operator_delivery_ledger_retry_entry_created: boolean;
  operator_delivery_ledger_dead_letter_entry_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  operator_notification_delivery_result_reconciliation_allowed: boolean;
  operator_notification_delivery_outcome_record_created: boolean;
  operator_notification_delivery_reconciliation_entry_created: boolean;
  operator_notification_delivery_retry_decision_created: boolean;
  operator_notification_dead_letter_entry_created: boolean;
  operator_notification_delivery_apply_allowed: boolean;
  operator_notification_delivery_transaction_created: boolean;
  operator_notification_dispatch_created: boolean;
  operator_notification_payload_created: boolean;
  operator_delivery_channel_policy_created: boolean;
  operator_notification_template_created: boolean;
  operator_notification_audit_entry_created: boolean;
  operator_notification_delivery_attempt_created: boolean;
  operator_notification_delivery_result_created: boolean;
  operator_notification_delivery_status_created: boolean;
  operator_notification_retry_policy_created: boolean;
  operator_notification_dead_letter_created: boolean;
  operator_notification_delivery_readiness_allowed: boolean;
  delivery_notification_created: boolean;
  run_closeout_record_created: boolean;
  final_run_closure_allowed: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilDeliveryNotificationReconciliationPlanRequest
  extends MidnightOilWorkspaceDeliveryCardReconciliationPlanRequest {
  workspace_delivery_card_reconciliation_plan_receipt: MidnightOilWorkspaceDeliveryCardReconciliationPlanReceipt;
}

export interface MidnightOilDeliveryNotificationReconciliationPlanReceipt {
  receipt_id: string;
  workspace_delivery_card_reconciliation_plan_receipt_id: string;
  operator_delivery_ledger_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_result_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_apply_plan_receipt_id: string;
  operator_notification_delivery_readiness_plan_receipt_id: string;
  final_run_closure_plan_receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_delivery_notification_reconciliation_unimplemented";
  adapter_key: "delivery_notification_reconciliation";
  planned_delivery_notification_reconciliation_receipt_id: string;
  planned_delivery_notification_id: string;
  planned_delivery_notification_status_entry_id: string;
  planned_delivery_notification_result_entry_id: string;
  planned_delivery_notification_operator_visible_event_id: string;
  planned_delivery_notification_replay_guard_id: string;
  planned_workspace_delivery_card_reconciliation_receipt_id: string;
  planned_workspace_delivery_card_id: string;
  planned_workspace_delivery_card_result_entry_id: string;
  planned_workspace_delivery_card_status_entry_id: string;
  planned_workspace_delivery_card_notification_entry_id: string;
  planned_workspace_delivery_card_replay_guard_id: string;
  planned_operator_delivery_ledger_reconciliation_receipt_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_operator_delivery_ledger_result_entry_id: string;
  planned_operator_delivery_ledger_status_entry_id: string;
  planned_operator_delivery_ledger_retry_entry_id: string;
  planned_operator_delivery_ledger_dead_letter_entry_id: string;
  planned_operator_notification_delivery_outcome_record_id: string;
  planned_operator_notification_delivery_reconciliation_entry_id: string;
  planned_operator_notification_delivery_retry_decision_id: string;
  planned_operator_notification_dead_letter_entry_id: string;
  planned_operator_notification_delivery_result_id: string;
  planned_operator_notification_delivery_status_id: string;
  planned_private_read_url_id: string;
  planned_reading_workspace_entry_id: string;
  planned_hosted_html_asset_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_idempotency_key: string;
  delivery_notification_reconciliation_blockers: string[];
  required_delivery_notification_reconciliation_invariants: string[];
  required_delivery_notification_reconciliation_receipt_fields: string[];
  blocker_reason: "delivery_notification_reconciliation_unimplemented";
  delivery_notification_reconciliation_allowed: boolean;
  delivery_notification_status_entry_created: boolean;
  delivery_notification_result_entry_created: boolean;
  delivery_notification_operator_visible_event_created: boolean;
  delivery_notification_created: boolean;
  workspace_delivery_card_reconciliation_allowed: boolean;
  workspace_delivery_card_result_entry_created: boolean;
  workspace_delivery_card_status_entry_created: boolean;
  workspace_delivery_card_notification_entry_created: boolean;
  workspace_delivery_card_created: boolean;
  operator_delivery_ledger_reconciliation_allowed: boolean;
  operator_delivery_ledger_result_entry_created: boolean;
  operator_delivery_ledger_status_entry_created: boolean;
  operator_delivery_ledger_retry_entry_created: boolean;
  operator_delivery_ledger_dead_letter_entry_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  operator_notification_delivery_result_reconciliation_allowed: boolean;
  operator_notification_delivery_outcome_record_created: boolean;
  operator_notification_delivery_reconciliation_entry_created: boolean;
  operator_notification_delivery_retry_decision_created: boolean;
  operator_notification_dead_letter_entry_created: boolean;
  operator_notification_delivery_apply_allowed: boolean;
  operator_notification_delivery_transaction_created: boolean;
  operator_notification_dispatch_created: boolean;
  operator_notification_payload_created: boolean;
  operator_delivery_channel_policy_created: boolean;
  operator_notification_template_created: boolean;
  operator_notification_audit_entry_created: boolean;
  operator_notification_delivery_attempt_created: boolean;
  operator_notification_delivery_result_created: boolean;
  operator_notification_delivery_status_created: boolean;
  operator_notification_retry_policy_created: boolean;
  operator_notification_dead_letter_created: boolean;
  operator_notification_delivery_readiness_allowed: boolean;
  run_closeout_record_created: boolean;
  final_run_closure_allowed: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilRetentionBillingReconciliationPlanRequest
  extends MidnightOilDeliveryNotificationReconciliationPlanRequest {
  delivery_notification_reconciliation_plan_receipt: MidnightOilDeliveryNotificationReconciliationPlanReceipt;
}

export interface MidnightOilRetentionBillingReconciliationPlanReceipt {
  receipt_id: string;
  delivery_notification_reconciliation_plan_receipt_id: string;
  workspace_delivery_card_reconciliation_plan_receipt_id: string;
  operator_delivery_ledger_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_result_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_apply_plan_receipt_id: string;
  operator_notification_delivery_readiness_plan_receipt_id: string;
  final_run_closure_plan_receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_retention_billing_reconciliation_unimplemented";
  adapter_key: "retention_billing_reconciliation";
  planned_retention_billing_reconciliation_receipt_id: string;
  planned_run_retention_manifest_id: string;
  planned_billing_reconciliation_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_run_retention_manifest_status_entry_id: string;
  planned_billing_reconciliation_status_entry_id: string;
  planned_model_usage_rollup_reconciliation_entry_id: string;
  planned_source_lineage_archive_reconciliation_entry_id: string;
  planned_delivery_notification_reconciliation_receipt_id: string;
  planned_delivery_notification_id: string;
  planned_delivery_notification_status_entry_id: string;
  planned_delivery_notification_result_entry_id: string;
  planned_delivery_notification_operator_visible_event_id: string;
  planned_delivery_notification_replay_guard_id: string;
  planned_workspace_delivery_card_reconciliation_receipt_id: string;
  planned_workspace_delivery_card_id: string;
  planned_operator_delivery_ledger_reconciliation_receipt_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_operator_delivery_ledger_status_entry_id: string;
  planned_operator_notification_delivery_outcome_record_id: string;
  planned_operator_notification_delivery_reconciliation_entry_id: string;
  planned_private_read_url_id: string;
  planned_reading_workspace_entry_id: string;
  planned_hosted_html_asset_id: string;
  planned_idempotency_key: string;
  retention_billing_reconciliation_blockers: string[];
  required_retention_billing_reconciliation_invariants: string[];
  required_retention_billing_reconciliation_receipt_fields: string[];
  blocker_reason: "retention_billing_reconciliation_unimplemented";
  retention_billing_reconciliation_allowed: boolean;
  run_retention_manifest_created: boolean;
  billing_reconciliation_created: boolean;
  model_usage_rollup_created: boolean;
  source_lineage_archive_created: boolean;
  run_retention_manifest_status_entry_created: boolean;
  billing_reconciliation_status_entry_created: boolean;
  model_usage_rollup_reconciliation_entry_created: boolean;
  source_lineage_archive_reconciliation_entry_created: boolean;
  delivery_notification_reconciliation_allowed: boolean;
  delivery_notification_status_entry_created: boolean;
  delivery_notification_result_entry_created: boolean;
  delivery_notification_operator_visible_event_created: boolean;
  delivery_notification_created: boolean;
  workspace_delivery_card_reconciliation_allowed: boolean;
  workspace_delivery_card_result_entry_created: boolean;
  workspace_delivery_card_status_entry_created: boolean;
  workspace_delivery_card_notification_entry_created: boolean;
  workspace_delivery_card_created: boolean;
  operator_delivery_ledger_reconciliation_allowed: boolean;
  operator_delivery_ledger_result_entry_created: boolean;
  operator_delivery_ledger_status_entry_created: boolean;
  operator_delivery_ledger_retry_entry_created: boolean;
  operator_delivery_ledger_dead_letter_entry_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  operator_notification_delivery_result_reconciliation_allowed: boolean;
  operator_notification_delivery_outcome_record_created: boolean;
  operator_notification_delivery_reconciliation_entry_created: boolean;
  operator_notification_delivery_retry_decision_created: boolean;
  operator_notification_dead_letter_entry_created: boolean;
  operator_notification_delivery_apply_allowed: boolean;
  operator_notification_delivery_transaction_created: boolean;
  operator_notification_dispatch_created: boolean;
  operator_notification_payload_created: boolean;
  operator_delivery_channel_policy_created: boolean;
  operator_notification_template_created: boolean;
  operator_notification_audit_entry_created: boolean;
  operator_notification_delivery_attempt_created: boolean;
  operator_notification_delivery_result_created: boolean;
  operator_notification_delivery_status_created: boolean;
  operator_notification_retry_policy_created: boolean;
  operator_notification_dead_letter_created: boolean;
  operator_notification_delivery_readiness_allowed: boolean;
  run_closeout_record_created: boolean;
  final_run_closure_allowed: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilFinalCloseoutArchiveReconciliationPlanRequest
  extends MidnightOilRetentionBillingReconciliationPlanRequest {
  retention_billing_reconciliation_plan_receipt: MidnightOilRetentionBillingReconciliationPlanReceipt;
}

export interface MidnightOilFinalCloseoutArchiveReconciliationPlanReceipt {
  receipt_id: string;
  retention_billing_reconciliation_plan_receipt_id: string;
  delivery_notification_reconciliation_plan_receipt_id: string;
  workspace_delivery_card_reconciliation_plan_receipt_id: string;
  operator_delivery_ledger_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_result_reconciliation_plan_receipt_id: string;
  operator_notification_delivery_apply_plan_receipt_id: string;
  operator_notification_delivery_readiness_plan_receipt_id: string;
  final_run_closure_plan_receipt_id: string;
  final_artifact_completion_finalization_plan_receipt_id: string;
  final_artifact_publish_plan_receipt_id: string;
  launch_packet_id: string;
  approval_receipt_id: string;
  runner_handoff_id: string;
  run_id: string;
  status: "blocked_final_closeout_archive_reconciliation_unimplemented";
  adapter_key: "final_closeout_archive_reconciliation";
  planned_final_closeout_archive_reconciliation_receipt_id: string;
  planned_final_run_closure_receipt_id: string;
  planned_run_closeout_record_id: string;
  planned_artifact_archive_manifest_id: string;
  planned_operator_handoff_summary_id: string;
  planned_quality_attestation_id: string;
  planned_completion_audit_entry_id: string;
  planned_retention_billing_reconciliation_receipt_id: string;
  planned_run_retention_manifest_id: string;
  planned_billing_reconciliation_id: string;
  planned_model_usage_rollup_id: string;
  planned_source_lineage_archive_id: string;
  planned_source_lineage_archive_reconciliation_entry_id: string;
  planned_delivery_notification_reconciliation_receipt_id: string;
  planned_delivery_notification_id: string;
  planned_workspace_delivery_card_id: string;
  planned_operator_delivery_ledger_entry_id: string;
  planned_private_read_url_id: string;
  planned_hosted_html_asset_id: string;
  planned_idempotency_key: string;
  final_closeout_archive_reconciliation_blockers: string[];
  required_final_closeout_archive_reconciliation_invariants: string[];
  required_final_closeout_archive_reconciliation_receipt_fields: string[];
  blocker_reason: "final_closeout_archive_reconciliation_unimplemented";
  final_closeout_archive_reconciliation_allowed: boolean;
  final_run_closure_receipt_reconciled: boolean;
  run_closeout_record_reconciled: boolean;
  artifact_archive_manifest_reconciled: boolean;
  operator_handoff_summary_reconciled: boolean;
  quality_attestation_reconciled: boolean;
  completion_audit_entry_reconciled: boolean;
  retention_billing_reconciliation_allowed: boolean;
  run_retention_manifest_created: boolean;
  billing_reconciliation_created: boolean;
  model_usage_rollup_created: boolean;
  source_lineage_archive_created: boolean;
  run_retention_manifest_status_entry_created: boolean;
  billing_reconciliation_status_entry_created: boolean;
  model_usage_rollup_reconciliation_entry_created: boolean;
  source_lineage_archive_reconciliation_entry_created: boolean;
  delivery_notification_reconciliation_allowed: boolean;
  delivery_notification_status_entry_created: boolean;
  delivery_notification_result_entry_created: boolean;
  delivery_notification_operator_visible_event_created: boolean;
  delivery_notification_created: boolean;
  workspace_delivery_card_reconciliation_allowed: boolean;
  workspace_delivery_card_result_entry_created: boolean;
  workspace_delivery_card_status_entry_created: boolean;
  workspace_delivery_card_notification_entry_created: boolean;
  workspace_delivery_card_created: boolean;
  operator_delivery_ledger_reconciliation_allowed: boolean;
  operator_delivery_ledger_result_entry_created: boolean;
  operator_delivery_ledger_status_entry_created: boolean;
  operator_delivery_ledger_retry_entry_created: boolean;
  operator_delivery_ledger_dead_letter_entry_created: boolean;
  operator_delivery_ledger_entry_created: boolean;
  run_closeout_record_created: boolean;
  final_run_closure_allowed: boolean;
  final_artifact_completion_finalization_allowed: boolean;
  completion_record_created: boolean;
  finalization_transaction_created: boolean;
  artifact_archive_manifest_created: boolean;
  operator_handoff_summary_created: boolean;
  delivery_status_marked_complete: boolean;
  quality_attestation_created: boolean;
  completion_audit_entry_created: boolean;
  final_artifact_publish_allowed: boolean;
  publish_transaction_created: boolean;
  information_asset_published: boolean;
  account_visible_asset_created: boolean;
  reading_workspace_entry_created: boolean;
  search_index_entry_created: boolean;
  private_read_url_created: boolean;
  operator_notification_created: boolean;
  graph_commit_created: boolean;
  graph_mutated: boolean;
  final_artifact_created: boolean;
  dispatch_performed: boolean;
  budget_reserved: boolean;
  provider_calls_made: boolean;
  retrieval_performed: boolean;
  source_receipts_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchiveHandoffPackagePlanRequest
  extends MidnightOilFinalCloseoutArchiveReconciliationPlanRequest {
  final_closeout_archive_reconciliation_plan_receipt: MidnightOilFinalCloseoutArchiveReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchiveHandoffPackagePlanReceipt
  extends Omit<
    MidnightOilFinalCloseoutArchiveReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  final_closeout_archive_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_handoff_package_unimplemented";
  adapter_key: "operator_archive_handoff_package";
  planned_operator_archive_handoff_package_receipt_id: string;
  planned_operator_archive_package_id: string;
  planned_operator_archive_manifest_id: string;
  planned_operator_handoff_bundle_id: string;
  operator_archive_handoff_package_blockers: string[];
  required_operator_archive_handoff_package_invariants: string[];
  required_operator_archive_handoff_package_receipt_fields: string[];
  blocker_reason: "operator_archive_handoff_package_unimplemented";
  operator_archive_handoff_package_allowed: boolean;
  operator_archive_package_created: boolean;
  operator_archive_manifest_created: boolean;
  operator_handoff_bundle_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanRequest
  extends MidnightOilOperatorArchiveHandoffPackagePlanRequest {
  operator_archive_handoff_package_plan_receipt: MidnightOilOperatorArchiveHandoffPackagePlanReceipt;
}

export interface MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchiveHandoffPackagePlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_handoff_package_plan_receipt_id: string;
  status: "blocked_operator_archive_handoff_package_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_handoff_package_result_reconciliation";
  planned_operator_archive_handoff_package_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_result_entry_id: string;
  planned_operator_archive_manifest_status_entry_id: string;
  planned_operator_handoff_bundle_status_entry_id: string;
  operator_archive_handoff_package_result_reconciliation_blockers: string[];
  required_operator_archive_handoff_package_result_reconciliation_invariants: string[];
  required_operator_archive_handoff_package_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_handoff_package_result_reconciliation_unimplemented";
  operator_archive_handoff_package_result_reconciliation_allowed: boolean;
  operator_archive_package_result_entry_created: boolean;
  operator_archive_manifest_status_entry_created: boolean;
  operator_handoff_bundle_status_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanRequest
  extends MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanRequest {
  operator_archive_handoff_package_result_reconciliation_plan_receipt: MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt
  extends Omit<
    MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_handoff_package_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_handoff_package_delivery_audit_unimplemented";
  adapter_key: "operator_archive_handoff_package_delivery_audit";
  planned_operator_archive_handoff_package_delivery_audit_receipt_id: string;
  planned_operator_archive_package_delivery_audit_entry_id: string;
  planned_operator_archive_manifest_delivery_audit_entry_id: string;
  planned_operator_handoff_bundle_delivery_audit_entry_id: string;
  planned_operator_archive_delivery_audit_evidence_bundle_id: string;
  operator_archive_handoff_package_delivery_audit_blockers: string[];
  required_operator_archive_handoff_package_delivery_audit_invariants: string[];
  required_operator_archive_handoff_package_delivery_audit_receipt_fields: string[];
  blocker_reason: "operator_archive_handoff_package_delivery_audit_unimplemented";
  operator_archive_handoff_package_delivery_audit_allowed: boolean;
  operator_archive_package_delivery_audit_entry_created: boolean;
  operator_archive_manifest_delivery_audit_entry_created: boolean;
  operator_handoff_bundle_delivery_audit_entry_created: boolean;
  operator_archive_delivery_audit_evidence_bundle_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanRequest
  extends MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanRequest {
  operator_archive_handoff_package_delivery_audit_plan_receipt: MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt;
}

export interface MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_handoff_package_delivery_audit_plan_receipt_id: string;
  status: "blocked_operator_archive_handoff_package_delivery_audit_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_handoff_package_delivery_audit_result_reconciliation";
  planned_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_audit_result_entry_id: string;
  planned_operator_archive_manifest_delivery_audit_status_entry_id: string;
  planned_operator_handoff_bundle_delivery_audit_status_entry_id: string;
  planned_operator_archive_delivery_audit_evidence_status_entry_id: string;
  operator_archive_handoff_package_delivery_audit_result_reconciliation_blockers: string[];
  required_operator_archive_handoff_package_delivery_audit_result_reconciliation_invariants: string[];
  required_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_handoff_package_delivery_audit_result_reconciliation_unimplemented";
  operator_archive_handoff_package_delivery_audit_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_audit_result_entry_created: boolean;
  operator_archive_manifest_delivery_audit_status_entry_created: boolean;
  operator_handoff_bundle_delivery_audit_status_entry_created: boolean;
  operator_archive_delivery_audit_evidence_status_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportPlanRequest
  extends MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanRequest {
  operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt: MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportPlanReceipt
  extends Omit<
    MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_unimplemented";
  adapter_key: "operator_archive_package_delivery_report";
  planned_operator_archive_package_delivery_report_receipt_id: string;
  planned_operator_archive_package_delivery_report_entry_id: string;
  planned_operator_archive_manifest_delivery_report_entry_id: string;
  planned_operator_handoff_bundle_delivery_report_entry_id: string;
  planned_operator_archive_delivery_report_evidence_bundle_id: string;
  operator_archive_package_delivery_report_blockers: string[];
  required_operator_archive_package_delivery_report_invariants: string[];
  required_operator_archive_package_delivery_report_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_unimplemented";
  operator_archive_package_delivery_report_allowed: boolean;
  operator_archive_package_delivery_report_entry_created: boolean;
  operator_archive_manifest_delivery_report_entry_created: boolean;
  operator_handoff_bundle_delivery_report_entry_created: boolean;
  operator_archive_delivery_report_evidence_bundle_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportPlanRequest {
  operator_archive_package_delivery_report_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_result_reconciliation";
  planned_operator_archive_package_delivery_report_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_result_entry_id: string;
  planned_operator_archive_manifest_delivery_report_status_entry_id: string;
  planned_operator_handoff_bundle_delivery_report_status_entry_id: string;
  planned_operator_archive_delivery_report_evidence_status_entry_id: string;
  operator_archive_package_delivery_report_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_result_entry_created: boolean;
  operator_archive_manifest_delivery_report_status_entry_created: boolean;
  operator_handoff_bundle_delivery_report_status_entry_created: boolean;
  operator_archive_delivery_report_evidence_status_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_notification_readiness_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_notification_readiness";
  planned_operator_archive_package_delivery_report_notification_readiness_receipt_id: string;
  planned_operator_archive_package_delivery_report_notification_payload_id: string;
  planned_operator_archive_package_delivery_report_notification_channel_policy_id: string;
  planned_operator_archive_package_delivery_report_notification_audit_id: string;
  operator_archive_package_delivery_report_notification_readiness_blockers: string[];
  required_operator_archive_package_delivery_report_notification_readiness_invariants: string[];
  required_operator_archive_package_delivery_report_notification_readiness_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_notification_readiness_unimplemented";
  operator_archive_package_delivery_report_notification_readiness_allowed: boolean;
  operator_archive_package_delivery_report_notification_payload_created: boolean;
  operator_archive_package_delivery_report_notification_channel_policy_created: boolean;
  operator_archive_package_delivery_report_notification_audit_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanRequest {
  operator_archive_package_delivery_report_notification_readiness_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_notification_readiness_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_notification_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_notification_result_reconciliation";
  planned_operator_archive_package_delivery_report_notification_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_notification_result_entry_id: string;
  planned_operator_archive_package_delivery_report_notification_status_entry_id: string;
  planned_operator_archive_package_delivery_report_notification_audit_status_entry_id: string;
  operator_archive_package_delivery_report_notification_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_notification_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_notification_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_notification_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_notification_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_notification_result_entry_created: boolean;
  operator_archive_package_delivery_report_notification_status_entry_created: boolean;
  operator_archive_package_delivery_report_notification_audit_status_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_delivery_confirmation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_delivery_confirmation";
  planned_operator_archive_package_delivery_report_delivery_confirmation_receipt_id: string;
  planned_operator_archive_package_delivery_report_delivery_confirmation_entry_id: string;
  planned_operator_archive_package_delivery_report_delivery_confirmation_status_entry_id: string;
  planned_operator_archive_package_delivery_report_delivery_confirmation_audit_entry_id: string;
  operator_archive_package_delivery_report_delivery_confirmation_blockers: string[];
  required_operator_archive_package_delivery_report_delivery_confirmation_invariants: string[];
  required_operator_archive_package_delivery_report_delivery_confirmation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_delivery_confirmation_unimplemented";
  operator_archive_package_delivery_report_delivery_confirmation_allowed: boolean;
  operator_archive_package_delivery_report_delivery_confirmation_entry_created: boolean;
  operator_archive_package_delivery_report_delivery_confirmation_status_entry_created: boolean;
  operator_archive_package_delivery_report_delivery_confirmation_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanRequest {
  operator_archive_package_delivery_report_delivery_confirmation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_delivery_confirmation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation";
  planned_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_delivery_confirmation_result_entry_id: string;
  planned_operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_id: string;
  operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_delivery_confirmation_result_entry_created: boolean;
  operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_operator_acknowledgement_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_operator_acknowledgement";
  planned_operator_archive_package_delivery_report_final_operator_acknowledgement_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_operator_acknowledgement_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_id: string;
  operator_archive_package_delivery_report_final_operator_acknowledgement_blockers: string[];
  required_operator_archive_package_delivery_report_final_operator_acknowledgement_invariants: string[];
  required_operator_archive_package_delivery_report_final_operator_acknowledgement_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_operator_acknowledgement_unimplemented";
  operator_archive_package_delivery_report_final_operator_acknowledgement_allowed: boolean;
  operator_archive_package_delivery_report_final_operator_acknowledgement_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanRequest {
  operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_acknowledgement_result_reconciliation";
  planned_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_acknowledgement_result_entry_id: string;
  planned_operator_archive_package_delivery_report_acknowledgement_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_acknowledgement_audit_result_entry_id: string;
  operator_archive_package_delivery_report_acknowledgement_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_acknowledgement_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_acknowledgement_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_acknowledgement_result_entry_created: boolean;
  operator_archive_package_delivery_report_acknowledgement_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_acknowledgement_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_closeout_acknowledgement_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_closeout_acknowledgement";
  planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_id: string;
  planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_id: string;
  operator_archive_package_delivery_report_final_closeout_acknowledgement_blockers: string[];
  required_operator_archive_package_delivery_report_final_closeout_acknowledgement_invariants: string[];
  required_operator_archive_package_delivery_report_final_closeout_acknowledgement_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_closeout_acknowledgement_unimplemented";
  operator_archive_package_delivery_report_final_closeout_acknowledgement_allowed: boolean;
  operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_created: boolean;
  operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanRequest {
  operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_operator_delivery_closeout_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_operator_delivery_closeout";
  planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_id: string;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_blockers: string[];
  required_operator_archive_package_delivery_report_final_operator_delivery_closeout_invariants: string[];
  required_operator_archive_package_delivery_report_final_operator_delivery_closeout_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_operator_delivery_closeout_unimplemented";
  operator_archive_package_delivery_report_final_operator_delivery_closeout_allowed: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanRequest {
  operator_archive_package_delivery_report_final_operator_delivery_closeout_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation";
  planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_result_entry_id: string;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_audit_envelope_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_audit_envelope";
  planned_operator_archive_package_delivery_report_final_delivery_audit_envelope_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_audit_envelope_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_audit_envelope_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_audit_envelope_audit_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_audit_envelope_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_audit_envelope_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_audit_envelope_unimplemented";
  operator_archive_package_delivery_report_final_delivery_audit_envelope_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanRequest {
  operator_archive_package_delivery_report_final_delivery_audit_envelope_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation";
  planned_operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_audit_envelope_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_audit_envelope_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_audit_envelope_audit_result_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_audit_envelope_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_dispatch_attestation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_dispatch_attestation";
  planned_operator_archive_package_delivery_report_final_dispatch_attestation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_dispatch_attestation_entry_id: string;
  planned_operator_archive_package_delivery_report_final_dispatch_attestation_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_dispatch_attestation_audit_entry_id: string;
  operator_archive_package_delivery_report_final_dispatch_attestation_blockers: string[];
  required_operator_archive_package_delivery_report_final_dispatch_attestation_invariants: string[];
  required_operator_archive_package_delivery_report_final_dispatch_attestation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_dispatch_attestation_unimplemented";
  operator_archive_package_delivery_report_final_dispatch_attestation_allowed: boolean;
  operator_archive_package_delivery_report_final_dispatch_attestation_entry_created: boolean;
  operator_archive_package_delivery_report_final_dispatch_attestation_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_dispatch_attestation_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationPlanRequest {
  operator_archive_package_delivery_report_final_dispatch_attestation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_dispatch_attestation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation";
  planned_operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_dispatch_attestation_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_dispatch_attestation_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_dispatch_attestation_audit_result_entry_id: string;
  operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_final_dispatch_attestation_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_dispatch_attestation_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_dispatch_attestation_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_dispatch_attestation_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_evidence_seal_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_evidence_seal";
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_audit_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_evidence_seal_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_evidence_seal_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_evidence_seal_unimplemented";
  operator_archive_package_delivery_report_final_delivery_evidence_seal_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanRequest {
  operator_archive_package_delivery_report_final_delivery_evidence_seal_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement";
  planned_operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_audit_entry_id: string;
  operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_blockers: string[];
  required_operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_invariants: string[];
  required_operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_unimplemented";
  operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_allowed: boolean;
  operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanRequest {
  operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_operator_archive_seal_acknowledgement_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation";
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_audit_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_unimplemented";
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanRequest {
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation";
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_audit_result_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_evidence_seal_attestation_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle";
  planned_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_audit_entry_id: string;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_blockers: string[];
  required_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_invariants: string[];
  required_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_unimplemented";
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_allowed: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanRequest {
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation";
  planned_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_audit_result_entry_id: string;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_operator_delivery_acknowledgement_bundle_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_handoff_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_handoff";
  planned_operator_archive_package_delivery_report_final_delivery_handoff_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_audit_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_handoff_unimplemented";
  operator_archive_package_delivery_report_final_delivery_handoff_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanRequest {
  operator_archive_package_delivery_report_final_delivery_handoff_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation";
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_audit_result_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanRequest {
  operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_result_reconciliation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_handoff_result_persistence";
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_ledger_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_audit_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_unimplemented";
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_ledger_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanRequest {
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation";
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_status_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_audit_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_unimplemented";
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_status_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_audit_entry_created: boolean;
  adapter_plan_notes: string[];
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationResultReconciliationPlanRequest
  extends MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanRequest {
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_plan_receipt: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanReceipt;
}

export interface MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationResultReconciliationPlanReceipt
  extends Omit<
    MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanReceipt,
    "receipt_id" | "status" | "adapter_key" | "blocker_reason" | "adapter_plan_notes"
  > {
  receipt_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_plan_receipt_id: string;
  status: "blocked_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_reconciliation_unimplemented";
  adapter_key: "operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_reconciliation";
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_reconciliation_receipt_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_status_result_entry_id: string;
  planned_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_audit_result_entry_id: string;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_reconciliation_blockers: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_reconciliation_invariants: string[];
  required_operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_reconciliation_receipt_fields: string[];
  blocker_reason: "operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_reconciliation_unimplemented";
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_reconciliation_allowed: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_status_result_entry_created: boolean;
  operator_archive_package_delivery_report_final_delivery_handoff_result_persistence_audit_attestation_audit_result_entry_created: boolean;
  adapter_plan_notes: string[];
}

export async function preflightMidnightOil(
  request: MidnightOilRequest,
): Promise<MidnightOilPreflight> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/preflight`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/preflight: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilPreflight;
}

export async function dryRunMidnightOil(
  request: MidnightOilDryRunRequest,
): Promise<MidnightOilAppliedRunReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/dry-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/dry-run: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilAppliedRunReceipt;
}

export async function liveRunActivationSettingsMidnightOil(
  request: MidnightOilLiveRunActivationSettingsRequest,
): Promise<MidnightOilLiveRunActivationSettingsReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/live-run-activation-settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/live-run-activation-settings: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilLiveRunActivationSettingsReceipt;
}

export async function dispatchMidnightOil(
  request: MidnightOilDispatchRequest,
): Promise<MidnightOilDispatchReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/dispatch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/dispatch: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilDispatchReceipt;
}

export async function activationChecklistMidnightOil(
  request: MidnightOilActivationChecklistRequest,
): Promise<MidnightOilActivationChecklistReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/activation-checklist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/activation-checklist: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilActivationChecklistReceipt;
}

export async function budgetReservationMidnightOil(
  request: MidnightOilBudgetReservationRequest,
): Promise<MidnightOilBudgetReservationReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/budget-reservation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/budget-reservation: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilBudgetReservationReceipt;
}

export async function providerRouteMidnightOil(
  request: MidnightOilProviderRouteRequest,
): Promise<MidnightOilProviderRouteReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/provider-route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/provider-route: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilProviderRouteReceipt;
}

export async function retrievalMidnightOil(
  request: MidnightOilRetrievalRequest,
): Promise<MidnightOilRetrievalReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/retrieval`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/retrieval: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilRetrievalReceipt;
}

export async function graphMutationMidnightOil(
  request: MidnightOilGraphMutationRequest,
): Promise<MidnightOilGraphMutationReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/graph-mutation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/graph-mutation: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilGraphMutationReceipt;
}

export async function finalArtifactMidnightOil(
  request: MidnightOilFinalArtifactRequest,
): Promise<MidnightOilFinalArtifactReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/final-artifact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/final-artifact: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilFinalArtifactReceipt;
}

export async function runnerReadinessMidnightOil(
  request: MidnightOilRunnerReadinessRequest,
): Promise<MidnightOilRunnerReadinessReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/runner-readiness`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/runner-readiness: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilRunnerReadinessReceipt;
}

export async function runnerControlPlanMidnightOil(
  request: MidnightOilRunnerControlPlanRequest,
): Promise<MidnightOilRunnerControlPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/runner-control-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /research/midnight-oil/runner-control-plan: HTTP ${resp.status}: ${body}`);
  }
  return (await resp.json()) as MidnightOilRunnerControlPlanReceipt;
}

export async function budgetProviderAdapterPlanMidnightOil(
  request: MidnightOilBudgetProviderAdapterPlanRequest,
): Promise<MidnightOilBudgetProviderAdapterPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/budget-provider-adapter-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/budget-provider-adapter-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilBudgetProviderAdapterPlanReceipt;
}

export async function providerExecutorAdapterPlanMidnightOil(
  request: MidnightOilProviderExecutorAdapterPlanRequest,
): Promise<MidnightOilProviderExecutorAdapterPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/provider-executor-adapter-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/provider-executor-adapter-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilProviderExecutorAdapterPlanReceipt;
}

export async function retrievalAdapterPlanMidnightOil(
  request: MidnightOilRetrievalAdapterPlanRequest,
): Promise<MidnightOilRetrievalAdapterPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/retrieval-adapter-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/retrieval-adapter-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilRetrievalAdapterPlanReceipt;
}

export async function graphAdapterPlanMidnightOil(
  request: MidnightOilGraphAdapterPlanRequest,
): Promise<MidnightOilGraphAdapterPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/graph-adapter-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/graph-adapter-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilGraphAdapterPlanReceipt;
}

export async function finalArtifactAdapterPlanMidnightOil(
  request: MidnightOilFinalArtifactAdapterPlanRequest,
): Promise<MidnightOilFinalArtifactAdapterPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/final-artifact-adapter-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-artifact-adapter-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalArtifactAdapterPlanReceipt;
}

export async function operatorDispatchAdapterPlanMidnightOil(
  request: MidnightOilOperatorDispatchAdapterPlanRequest,
): Promise<MidnightOilOperatorDispatchAdapterPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/operator-dispatch-adapter-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-dispatch-adapter-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorDispatchAdapterPlanReceipt;
}

export async function controlLedgerAdapterPlanMidnightOil(
  request: MidnightOilControlLedgerAdapterPlanRequest,
): Promise<MidnightOilControlLedgerAdapterPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/control-ledger-adapter-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/control-ledger-adapter-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilControlLedgerAdapterPlanReceipt;
}

export async function controlLedgerPersistencePlanMidnightOil(
  request: MidnightOilControlLedgerPersistencePlanRequest,
): Promise<MidnightOilControlLedgerPersistencePlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/control-ledger-persistence-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/control-ledger-persistence-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilControlLedgerPersistencePlanReceipt;
}

export async function controlLedgerPersistenceApplyPlanMidnightOil(
  request: MidnightOilControlLedgerPersistenceApplyPlanRequest,
): Promise<MidnightOilControlLedgerPersistenceApplyPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/control-ledger-persistence-apply-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/control-ledger-persistence-apply-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilControlLedgerPersistenceApplyPlanReceipt;
}

export async function operatorDispatchActivationReadinessPlanMidnightOil(
  request: MidnightOilOperatorDispatchActivationReadinessPlanRequest,
): Promise<MidnightOilOperatorDispatchActivationReadinessPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-dispatch-activation-readiness-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-dispatch-activation-readiness-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorDispatchActivationReadinessPlanReceipt;
}

export async function liveDispatchFinalEnablementPlanMidnightOil(
  request: MidnightOilLiveDispatchFinalEnablementPlanRequest,
): Promise<MidnightOilLiveDispatchFinalEnablementPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/live-dispatch-final-enablement-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/live-dispatch-final-enablement-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilLiveDispatchFinalEnablementPlanReceipt;
}

export async function liveDispatchFinalEnablementApplyPlanMidnightOil(
  request: MidnightOilLiveDispatchFinalEnablementApplyPlanRequest,
): Promise<MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/live-dispatch-final-enablement-apply-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/live-dispatch-final-enablement-apply-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt;
}

export async function runnerDispatchSchedulerPlanMidnightOil(
  request: MidnightOilRunnerDispatchSchedulerPlanRequest,
): Promise<MidnightOilRunnerDispatchSchedulerPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/runner-dispatch-scheduler-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/runner-dispatch-scheduler-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilRunnerDispatchSchedulerPlanReceipt;
}

export async function runnerDispatchWorkerBootstrapPlanMidnightOil(
  request: MidnightOilRunnerDispatchWorkerBootstrapPlanRequest,
): Promise<MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/runner-dispatch-worker-bootstrap-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/runner-dispatch-worker-bootstrap-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt;
}

export async function schedulerLeaseRetryPlanMidnightOil(
  request: MidnightOilSchedulerLeaseRetryPlanRequest,
): Promise<MidnightOilSchedulerLeaseRetryPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/scheduler-lease-retry-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/scheduler-lease-retry-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilSchedulerLeaseRetryPlanReceipt;
}

export async function workerQueueClaimPlanMidnightOil(
  request: MidnightOilWorkerQueueClaimPlanRequest,
): Promise<MidnightOilWorkerQueueClaimPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/worker-queue-claim-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/worker-queue-claim-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilWorkerQueueClaimPlanReceipt;
}

export async function repositoryTransactionPlanMidnightOil(
  request: MidnightOilRepositoryTransactionPlanRequest,
): Promise<MidnightOilRepositoryTransactionPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/repository-transaction-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/repository-transaction-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilRepositoryTransactionPlanReceipt;
}

export async function repositoryCommitRollbackPlanMidnightOil(
  request: MidnightOilRepositoryCommitRollbackPlanRequest,
): Promise<MidnightOilRepositoryCommitRollbackPlanReceipt> {
  const resp = await apiFetch(`${API_BASE}/research/midnight-oil/repository-commit-rollback-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/repository-commit-rollback-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilRepositoryCommitRollbackPlanReceipt;
}

export async function workerDispatchLeaseHeartbeatPlanMidnightOil(
  request: MidnightOilWorkerDispatchLeaseHeartbeatPlanRequest,
): Promise<MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/worker-dispatch-lease-heartbeat-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/worker-dispatch-lease-heartbeat-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt;
}

export async function workerCancellationAbandonPlanMidnightOil(
  request: MidnightOilWorkerCancellationAbandonPlanRequest,
): Promise<MidnightOilWorkerCancellationAbandonPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/worker-cancellation-abandon-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/worker-cancellation-abandon-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilWorkerCancellationAbandonPlanReceipt;
}

export async function workerCompletionFinalizationPlanMidnightOil(
  request: MidnightOilWorkerCompletionFinalizationPlanRequest,
): Promise<MidnightOilWorkerCompletionFinalizationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/worker-completion-finalization-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/worker-completion-finalization-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilWorkerCompletionFinalizationPlanReceipt;
}

export async function workerOutputAggregationPlanMidnightOil(
  request: MidnightOilWorkerOutputAggregationPlanRequest,
): Promise<MidnightOilWorkerOutputAggregationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/worker-output-aggregation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/worker-output-aggregation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilWorkerOutputAggregationPlanReceipt;
}

export async function workerSynthesisHandoffPlanMidnightOil(
  request: MidnightOilWorkerSynthesisHandoffPlanRequest,
): Promise<MidnightOilWorkerSynthesisHandoffPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/worker-synthesis-handoff-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/worker-synthesis-handoff-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilWorkerSynthesisHandoffPlanReceipt;
}

export async function synthesisBundleAssemblyPlanMidnightOil(
  request: MidnightOilSynthesisBundleAssemblyPlanRequest,
): Promise<MidnightOilSynthesisBundleAssemblyPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/synthesis-bundle-assembly-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/synthesis-bundle-assembly-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilSynthesisBundleAssemblyPlanReceipt;
}

export async function finalSynthesisDraftPlanMidnightOil(
  request: MidnightOilFinalSynthesisDraftPlanRequest,
): Promise<MidnightOilFinalSynthesisDraftPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/final-synthesis-draft-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-synthesis-draft-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalSynthesisDraftPlanReceipt;
}

export async function finalHtmlArtifactAssemblyPlanMidnightOil(
  request: MidnightOilFinalHtmlArtifactAssemblyPlanRequest,
): Promise<MidnightOilFinalHtmlArtifactAssemblyPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/final-html-artifact-assembly-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-html-artifact-assembly-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalHtmlArtifactAssemblyPlanReceipt;
}

export async function finalArtifactPersistencePlanMidnightOil(
  request: MidnightOilFinalArtifactPersistencePlanRequest,
): Promise<MidnightOilFinalArtifactPersistencePlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/final-artifact-persistence-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-artifact-persistence-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalArtifactPersistencePlanReceipt;
}

export async function finalArtifactGraphCommitPlanMidnightOil(
  request: MidnightOilFinalArtifactGraphCommitPlanRequest,
): Promise<MidnightOilFinalArtifactGraphCommitPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/final-artifact-graph-commit-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-artifact-graph-commit-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalArtifactGraphCommitPlanReceipt;
}

export async function finalArtifactPublishPlanMidnightOil(
  request: MidnightOilFinalArtifactPublishPlanRequest,
): Promise<MidnightOilFinalArtifactPublishPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/final-artifact-publish-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-artifact-publish-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalArtifactPublishPlanReceipt;
}

export async function finalArtifactCompletionFinalizationPlanMidnightOil(
  request: MidnightOilFinalArtifactCompletionFinalizationPlanRequest,
): Promise<MidnightOilFinalArtifactCompletionFinalizationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/final-artifact-completion-finalization-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-artifact-completion-finalization-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalArtifactCompletionFinalizationPlanReceipt;
}

export async function finalRunClosurePlanMidnightOil(
  request: MidnightOilFinalRunClosurePlanRequest,
): Promise<MidnightOilFinalRunClosurePlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/final-run-closure-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-run-closure-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalRunClosurePlanReceipt;
}

export async function operatorNotificationDeliveryReadinessPlanMidnightOil(
  request: MidnightOilOperatorNotificationDeliveryReadinessPlanRequest,
): Promise<MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-notification-delivery-readiness-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-notification-delivery-readiness-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt;
}

export async function operatorNotificationDeliveryApplyPlanMidnightOil(
  request: MidnightOilOperatorNotificationDeliveryApplyPlanRequest,
): Promise<MidnightOilOperatorNotificationDeliveryApplyPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-notification-delivery-apply-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-notification-delivery-apply-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorNotificationDeliveryApplyPlanReceipt;
}

export async function operatorNotificationDeliveryResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorNotificationDeliveryResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-notification-delivery-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-notification-delivery-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt;
}

export async function operatorDeliveryLedgerReconciliationPlanMidnightOil(
  request: MidnightOilOperatorDeliveryLedgerReconciliationPlanRequest,
): Promise<MidnightOilOperatorDeliveryLedgerReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-delivery-ledger-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-delivery-ledger-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorDeliveryLedgerReconciliationPlanReceipt;
}

export async function workspaceDeliveryCardReconciliationPlanMidnightOil(
  request: MidnightOilWorkspaceDeliveryCardReconciliationPlanRequest,
): Promise<MidnightOilWorkspaceDeliveryCardReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/workspace-delivery-card-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/workspace-delivery-card-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilWorkspaceDeliveryCardReconciliationPlanReceipt;
}

export async function deliveryNotificationReconciliationPlanMidnightOil(
  request: MidnightOilDeliveryNotificationReconciliationPlanRequest,
): Promise<MidnightOilDeliveryNotificationReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/delivery-notification-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/delivery-notification-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilDeliveryNotificationReconciliationPlanReceipt;
}

export async function retentionBillingReconciliationPlanMidnightOil(
  request: MidnightOilRetentionBillingReconciliationPlanRequest,
): Promise<MidnightOilRetentionBillingReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/retention-billing-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/retention-billing-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilRetentionBillingReconciliationPlanReceipt;
}

export async function finalCloseoutArchiveReconciliationPlanMidnightOil(
  request: MidnightOilFinalCloseoutArchiveReconciliationPlanRequest,
): Promise<MidnightOilFinalCloseoutArchiveReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/final-closeout-archive-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/final-closeout-archive-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilFinalCloseoutArchiveReconciliationPlanReceipt;
}

export async function operatorArchiveHandoffPackagePlanMidnightOil(
  request: MidnightOilOperatorArchiveHandoffPackagePlanRequest,
): Promise<MidnightOilOperatorArchiveHandoffPackagePlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-handoff-package-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-handoff-package-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchiveHandoffPackagePlanReceipt;
}

export async function operatorArchiveHandoffPackageResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-handoff-package-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-handoff-package-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanReceipt;
}

export async function operatorArchiveHandoffPackageDeliveryAuditPlanMidnightOil(
  request: MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanRequest,
): Promise<MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-handoff-package-delivery-audit-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-handoff-package-delivery-audit-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt;
}

export async function operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-handoff-package-delivery-audit-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-handoff-package-delivery-audit-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportNotificationReadinessPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-notification-readiness-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-notification-readiness-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-notification-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-notification-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportDeliveryConfirmationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-delivery-confirmation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-delivery-confirmation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-delivery-confirmation-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-operator-acknowledgement-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-operator-acknowledgement-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-acknowledgement-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-closeout-acknowledgement-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-closeout-acknowledgement-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-operator-delivery-closeout-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-operator-delivery-closeout-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-operator-delivery-closeout-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-operator-delivery-closeout-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-audit-envelope-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-audit-envelope-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopePlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-audit-envelope-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-audit-envelope-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryAuditEnvelopeResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDispatchAttestationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-dispatch-attestation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-dispatch-attestation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-dispatch-attestation-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-dispatch-attestation-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDispatchAttestationResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-evidence-seal-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-evidence-seal-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-operator-archive-seal-acknowledgement-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-operator-archive-seal-acknowledgement-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorArchiveSealAcknowledgementPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-evidence-seal-attestation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-evidence-seal-attestation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-evidence-seal-attestation-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-evidence-seal-attestation-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryEvidenceSealAttestationResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-operator-delivery-acknowledgement-bundle-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-operator-delivery-acknowledgement-bundle-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundlePlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-operator-delivery-acknowledgement-bundle-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-operator-delivery-acknowledgement-bundle-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryAcknowledgementBundleResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultReconciliationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-result-persistence-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-result-persistence-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistencePlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-result-persistence-audit-attestation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-result-persistence-audit-attestation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationPlanReceipt;
}

export async function operatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationResultReconciliationPlanMidnightOil(
  request: MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationResultReconciliationPlanRequest,
): Promise<MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationResultReconciliationPlanReceipt> {
  const resp = await apiFetch(
    `${API_BASE}/research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-result-persistence-audit-attestation-result-reconciliation-plan`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(
      `POST /research/midnight-oil/operator-archive-package-delivery-report-final-delivery-handoff-result-persistence-audit-attestation-result-reconciliation-plan: HTTP ${resp.status}: ${body}`,
    );
  }
  return (await resp.json()) as MidnightOilOperatorArchivePackageDeliveryReportFinalDeliveryHandoffResultPersistenceAuditAttestationResultReconciliationPlanReceipt;
}
