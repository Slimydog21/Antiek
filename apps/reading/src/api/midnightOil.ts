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
