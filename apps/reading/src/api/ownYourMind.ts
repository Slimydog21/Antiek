/**
 * Own Your Mind P0 — read-only API client.
 *
 * Frontend half of docs/own-your-mind/10-p0-implementation-brief.md
 * (D1 why-this-claim, C1a objective-card, L15 signal-inventory). Five
 * additive GETs, no mutation endpoints:
 *
 *   GET /claims/{claim_node_id}/explain    — provenance chain behind one
 *                                            claim node (the claim, its
 *                                            supporting edges, chunk excerpts,
 *                                            source documents, tier overrides)
 *   GET /syntheses/{synthesis_id}/explain  — what grounded a synthesis,
 *                                            resolved via the
 *                                            synthesis_substrate_manifest pins
 *   GET /docs/{document_id}/explain        — reverse provenance: the
 *                                            document's chunks and the edges
 *                                            (with their source nodes) that
 *                                            cite those chunks
 *   GET /ops/objective-card                — live dispatch matrix, gap-scoring
 *                                            constants, retrieval gates,
 *                                            quality thresholds, budgets,
 *                                            reuse gate
 *   GET /ops/signal-inventory              — every ActionType with payload
 *                                            class + domain, generated from
 *                                            substrate/schemas/events.py
 *
 * Types mirror the backend payloads exactly:
 *   - interfaces/research/api/explain_routes.py
 *     (row shapes from substrate/graph/schema.py: nodes / edges / chunks /
 *     documents / chunk_tier_overrides / synthesis_substrate_manifest)
 *   - interfaces/research/api/ops_objective.py
 *   - interfaces/research/api/ops_signal_inventory.py
 *
 * This module is the single typed seam the three modes read from; if the
 * backend shapes drift, the fix belongs here.
 */

import { API_BASE, ApiError, apiFetch } from "../lib/api";

// ── Shared explain views (mirror explain_routes.py row resolvers) ───────

/** One ``nodes`` row — the entity being explained (a claim, typically). */
export interface ExplainNode {
  node_id: string;
  canonical_label: string | null;
  node_type: string | null;
  graph_scope: string | null;
  created_at: string | null;
}

/** One ``edges`` row — a supporting relation with its grounding citation.
 *  ``document_id`` is the edge's ``source_document_id`` (the backend
 *  renames it on the wire). */
export interface ExplainEdge {
  edge_id: string;
  source_node_id: string | null;
  target_node_id: string | null;
  relation: string;
  chunk_id: string | null;
  document_id: string | null;
  /** The edge's tier at extraction time (1 = strongest … 5 = weakest). */
  source_tier: number;
  extraction_confidence: number;
  graph_scope: string | null;
}

/** One ``chunks`` row. ``text`` is the excerpt (backend truncates to
 *  SERVE_SNIPPET_MAX_CHARS = 500). */
export interface ExplainChunk {
  chunk_id: string;
  document_id: string;
  section_path: string | null;
  text: string;
  chunk_index: number | null;
}

/** One ``documents`` row — the source a chunk/edge cites. */
export interface ExplainDocument {
  document_id: string;
  title: string | null;
  author: string | null;
  source_tier: number;
  acquired_at: string | null;
}

/** One ``chunk_tier_overrides`` row — who changed a chunk's tier and why. */
export interface TierOverride {
  chunk_id: string;
  original_tier: number;
  override_tier: number;
  set_by: string | null;
  reason: string;
  set_at: string | null;
}

// ── D1: /explain responses ─────────────────────────────────────────────

export interface ClaimExplainResponse {
  claim_node: ExplainNode;
  supporting_edges: ExplainEdge[];
  chunks: ExplainChunk[];
  documents: ExplainDocument[];
  chunk_tier_overrides: TierOverride[];
  generated_at: string;
}

/** One synthesis_substrate_manifest pin, resolved to its chain. */
export interface SynthesisPinBase {
  entity_id: string;
  pinned_at: string;
}

/** A pin whose entity no longer resolves — honest data drift, surfaced. */
export interface UnresolvedPin extends SynthesisPinBase {
  entity_kind: "document" | "chunk" | "node" | "edge";
  unresolved: true;
}

export interface DocumentPin extends SynthesisPinBase {
  entity_kind: "document";
  document: ExplainDocument;
}

export interface ChunkPin extends SynthesisPinBase {
  entity_kind: "chunk";
  chunk: ExplainChunk;
  documents: ExplainDocument[];
  chunk_tier_overrides: TierOverride[];
}

export interface EdgePin extends SynthesisPinBase {
  entity_kind: "edge";
  edge: ExplainEdge;
  chunks: ExplainChunk[];
  documents: ExplainDocument[];
  chunk_tier_overrides: TierOverride[];
}

export interface NodePin extends SynthesisPinBase {
  entity_kind: "node";
  claim_node: ExplainNode;
  supporting_edges: ExplainEdge[];
  chunks: ExplainChunk[];
  documents: ExplainDocument[];
  chunk_tier_overrides: TierOverride[];
}

export type SynthesisPin =
  | UnresolvedPin
  | DocumentPin
  | ChunkPin
  | EdgePin
  | NodePin;

export interface SynthesisExplainResponse {
  synthesis_id: string;
  /** Manifest pins grouped by entity_kind, in a fixed order. */
  pins: {
    document: SynthesisPin[];
    chunk: SynthesisPin[];
    node: SynthesisPin[];
    edge: SynthesisPin[];
  };
  generated_at: string;
}

export interface DocumentExplainResponse {
  document: ExplainDocument;
  chunks: ExplainChunk[];
  /** The edges that cite this document's chunks (reverse provenance). */
  citing_edges: ExplainEdge[];
  /** The source nodes of ``citing_edges`` (the claims that cite it). */
  citing_nodes: ExplainNode[];
  chunk_tier_overrides: TierOverride[];
  generated_at: string;
}

// ── C1a: /ops/objective-card ───────────────────────────────────────────

/** One dispatch tier entry from substrate/dispatch/config.yaml. The config
 *  entry carries NO name key (the name is the YAML map key); the row view
 *  adds ``name`` when the card flattens the map. */
export interface DispatchTierView {
  name: string;
  provider: string | null;
  model: string | null;
  /** Nested fallback chain (provider/model), rendered as a chain string. */
  fallback: RawDispatchTier | null;
  pricing: {
    input_per_mtok: number;
    output_per_mtok: number;
    cached_input_per_mtok: number;
  } | null;
}

/** The raw config.yaml tier shape — the wire payload of the ``tiers`` map. */
export type RawDispatchTier = Omit<DispatchTierView, "name">;

export interface DispatchSection {
  source: string;
  version: string | null;
  role_tiers: Record<string, string>;
  tiers: Record<string, RawDispatchTier>;
  tier_defaults: Record<string, Record<string, number>>;
  cost_tracking: Record<string, unknown> | null;
  /** True when every tier's pricing is all-zeros — "unverified", not free. */
  pricing_placeholder: boolean;
  pricing_note: string;
}

export interface GapScoringSection {
  constants: {
    MAX_CHASE_COUNT: number;
    RECENCY_HALF_LIFE_DAYS: number;
    CO_OCCURRENCE_CAP: number;
    INTERACTION_BOOST: number;
  };
  objective: string;
  daemon_spawn_params: {
    expected_cost_per_spawn_usd: number;
    max_spawns_per_iteration: number;
    min_score_to_spawn: number;
    spawn_policy_id: string | null;
    sleep_seconds: number;
  };
}

export interface RetrievalGatesSection {
  policy: string;
  privileged_policy_tags: string[];
  restricted_content_classes: string[];
  personal_only_content_classes: string[];
  non_privileged_excluded_content_classes: string[];
  note: string;
}

export interface QualityGateSection {
  checks: {
    verification: { rule: string };
    voice_style: { threshold: number };
    source_tier: { min_acceptable: number; max_acceptable: number; note: string };
    extraction_quality: { min_distinct_chars: number; note: string };
  };
  source: string;
}

export interface BudgetsSection {
  research_runner: { aggregate_cap_usd: number; scope: string };
  continuous_daemon: {
    per_investigation_cap_usd: number;
    default_daily_cap_usd: number;
    daily_cap_env_override: string;
    max_topic_depth: number;
    scope: string;
  };
}

export interface ReuseGateSection {
  groundedness_threshold: number;
  env_override: string;
  rule: string;
}

export interface ObjectiveCardResponse {
  generated_at: string;
  dispatch: DispatchSection;
  gap_scoring: GapScoringSection;
  retrieval_gates: RetrievalGatesSection;
  quality_gate: QualityGateSection;
  budgets: BudgetsSection;
  reuse_gate: ReuseGateSection;
}

// ── L15: /ops/signal-inventory ─────────────────────────────────────────

/** One ActionType from substrate/schemas/events.py. */
export interface SignalActionView {
  action_type: string;
  payload_class: string | null;
  typed: boolean;
  /** First dotted segment of the value (dispatch.call → dispatch). */
  domain: string;
  /** Emitter note — NOT in the P0 backend payload; reserved for when the
   *  component map publishes it. Rendered only when present. */
  emitted_by?: string | null;
}

export interface SignalInventoryResponse {
  generated_at: string;
  schema_version: number;
  count: number;
  signals: SignalActionView[];
  by_domain: Record<string, { count: number; action_types: string[] }>;
}

// ── Request helpers (same shape as api/research.ts) ────────────────────

async function get<T>(path: string): Promise<T> {
  const resp = await apiFetch(`${API_BASE}${path}`);
  if (!resp.ok) {
    throw new ApiError(
      `GET ${path} failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return resp.json() as Promise<T>;
}

// ── D1: provenance chains ──────────────────────────────────────────────

export function explainClaim(claimNodeId: string): Promise<ClaimExplainResponse> {
  return get(`/claims/${encodeURIComponent(claimNodeId)}/explain`);
}

export function explainSynthesis(
  synthesisId: string,
): Promise<SynthesisExplainResponse> {
  return get(`/syntheses/${encodeURIComponent(synthesisId)}/explain`);
}

export function explainDocument(
  documentId: string,
): Promise<DocumentExplainResponse> {
  return get(`/docs/${encodeURIComponent(documentId)}/explain`);
}

// ── C1a + L15: ops surfaces ────────────────────────────────────────────

export function getObjectiveCard(): Promise<ObjectiveCardResponse> {
  return get("/ops/objective-card");
}

export function getSignalInventory(): Promise<SignalInventoryResponse> {
  return get("/ops/signal-inventory");
}
