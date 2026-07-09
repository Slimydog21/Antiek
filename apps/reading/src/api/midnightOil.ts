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
