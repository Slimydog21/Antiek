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
  notes: string[];
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
