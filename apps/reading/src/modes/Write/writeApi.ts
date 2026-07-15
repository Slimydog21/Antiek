/**
 * Typed client for the Write REST surface (`/write/*`,
 * interfaces/research/api/write_routes.py).
 *
 * Kept in its own module (not the shared, multi-stream-edited lib/api.ts)
 * for the same collision-avoidance reason the router itself is a separate
 * file. Thin wrappers over the app's ``apiFetch`` (which carries the
 * Cloudflare Access cookies).
 */

import { API_BASE, ApiError, apiFetch } from "../../lib/api";
import { notifyOutlineBlockCommitted } from "../../werner/shellExperienceSignals";

export interface RepositoryHit {
  node_id: string;
  label: string;
  node_type: string;
  source_tier: number | null;
  document_id: string | null;
  document_title: string | null;
  score: number;
}

/** Preserve the graph node's semantic kind across tap and native drag paths. */
export function repositoryBlockKind(
  nodeType: string,
): "insight" | "open_question" | "claim" {
  if (nodeType === "claim") return "claim";
  if (nodeType === "question" || nodeType === "open_question") return "open_question";
  return "insight";
}

export interface FolderSummary {
  folder_id: string;
  name: string;
  member_count: number;
}

/** Place a graph-node-backed block (the dominant case — dragging an insight /
 * question / claim from research into the outline). Carries a node_id, no
 * content (the node is the content of record). */
export interface PlaceNodeBlockBody {
  section_id: string;
  block_kind: "insight" | "open_question" | "claim";
  provenance_kind: "graph_node";
  node_id: string;
  block_index: number;
  deliverable_id?: string;
}

/** Place a user-originated block (the operator wrote/spoke it — e.g. SPR-09 M4
 * voice-to-draft). §9: carries inline content + NO node_id (no fabricated
 * citation); recorded as the writer's own authorship, never model output. */
export interface PlaceUserBlockBody {
  section_id: string;
  block_kind: "user_authored" | "operator_note";
  provenance_kind: "user_authored";
  content: string;
  block_index: number;
  deliverable_id?: string;
}

export type PlaceBlockBody = PlaceNodeBlockBody | PlaceUserBlockBody;

async function _json<T>(resp: Response, what: string): Promise<T> {
  if (!resp.ok) {
    throw new ApiError(`${what} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
  return resp.json() as Promise<T>;
}

export async function searchRepository(opts: {
  q?: string;
  folderId?: string;
  sourceDocumentId?: string;
  limit?: number;
}): Promise<RepositoryHit[]> {
  const url = new URL(`${API_BASE}/write/blocks/search`, window.location.origin);
  if (opts.q) url.searchParams.set("q", opts.q);
  if (opts.folderId) url.searchParams.set("folder_id", opts.folderId);
  if (opts.sourceDocumentId) url.searchParams.set("source_document_id", opts.sourceDocumentId);
  if (opts.limit) url.searchParams.set("limit", String(opts.limit));
  const body = await _json<{ hits: RepositoryHit[] }>(
    await apiFetch(url.toString()), "GET /write/blocks/search",
  );
  return body.hits;
}

export async function listFolders(): Promise<FolderSummary[]> {
  const body = await _json<{ folders: FolderSummary[] }>(
    await apiFetch(`${API_BASE}/write/folders`), "GET /write/folders",
  );
  return body.folders;
}

export async function createFolder(name: string): Promise<string> {
  const body = await _json<{ folder_id: string }>(
    await apiFetch(`${API_BASE}/write/folders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
    "POST /write/folders",
  );
  return body.folder_id;
}

export async function addFolderBlock(folderId: string, nodeId: string): Promise<void> {
  await _json<unknown>(
    await apiFetch(`${API_BASE}/write/folders/${encodeURIComponent(folderId)}/blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId }),
    }),
    "POST /write/folders/{id}/blocks",
  );
}

/** Place a block in the outline (the drop target's commit). Returns the
 * new outline_block_id. */
export async function placeBlock(body: PlaceBlockBody): Promise<string> {
  const r = await _json<{ outline_block_id: string }>(
    await apiFetch(`${API_BASE}/write/blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "POST /write/blocks",
  );
  if (
    typeof r.outline_block_id !== "string" ||
    r.outline_block_id.trim().length === 0
  ) {
    throw new ApiError(
      "POST /write/blocks returned an invalid outline_block_id",
      502,
      JSON.stringify(r),
    );
  }
  notifyOutlineBlockCommitted();
  return r.outline_block_id;
}

/** One block as it sits in a section's outline.
 *
 * `node_label` is the node's text for a graph-node block (whose `content`
 * is null — the text lives on the node); the routed outline renders this,
 * NEVER the `outline_block_id` / `node_id` (SPR-07 M2 no-UUID gate). The
 * raw ids are present for the move/reorder API only, never for display. */
export interface OutlineBlockView {
  outline_block_id: string;
  section_id: string;
  block_kind: string;
  provenance_kind: string;
  node_id: string | null;
  /** User-authored prose, when this block isn't node-backed. */
  content: string | null;
  /** The node's canonical label, for a graph-node block. */
  node_label: string | null;
  block_index: number;
  is_user_originated: boolean;
}

/** The display text for an outline block — never an id. Falls back to a
 * plain placeholder rather than leaking a handle. */
export function blockDisplayText(b: OutlineBlockView): string {
  return (b.content || b.node_label || "").trim() || "(untitled block)";
}

/** Read a section's blocks (for the routed outline). */
export async function getSectionBlocks(
  sectionId: string,
): Promise<OutlineBlockView[]> {
  const body = await _json<{ blocks: OutlineBlockView[] }>(
    await apiFetch(`${API_BASE}/write/sections/${encodeURIComponent(sectionId)}/blocks`),
    "GET /write/sections/{id}/blocks",
  );
  return body.blocks;
}

/** Move/reorder a placed block within or across sections (drag-to-reorder). */
export async function moveBlock(
  outlineBlockId: string,
  toSectionId: string,
  toIndex: number,
): Promise<void> {
  await _json<unknown>(
    await apiFetch(`${API_BASE}/write/blocks/${encodeURIComponent(outlineBlockId)}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_section_id: toSectionId, to_index: toIndex }),
    }),
    "POST /write/blocks/{id}/move",
  );
}

export interface TraceTarget {
  kind: string;
  /** The no-leak bit: false ⟹ the source is gated, only metadata is shown. */
  full_text_allowed: boolean;
  document_id: string | null;
  document_title: string | null;
  chunk_ids: string[];
  servability_status: string | null;
  detail: string | null;
}

/** Resolve a placed block's trace target (the source the citation chip
 * opens). Honest about gating: `full_text_allowed=false` for a gated source
 * (§9.0 no-leak). The shared reader that opens it is DRW SPR-10. */
export async function getTraceTarget(outlineBlockId: string): Promise<TraceTarget> {
  return _json<TraceTarget>(
    await apiFetch(`${API_BASE}/write/blocks/${encodeURIComponent(outlineBlockId)}/trace`),
    "GET /write/blocks/{id}/trace",
  );
}

export interface PromoteResult {
  deliverable_id: string;
  section_id: string;
  block_ids: string[];
}

/** Promote a pre-outline context window to a structured outline (SPR-08). */
export async function promoteContext(body: unknown): Promise<PromoteResult> {
  return _json<PromoteResult>(
    await apiFetch(`${API_BASE}/write/context/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "POST /write/context/promote",
  );
}

export interface GenerationResult {
  status: "generated" | "gap" | "gate_failed" | "invalid";
  section_id: string;
  prose_text?: string;
  detail?: string;
  gate_passed?: boolean | null;
  all_claims_cited?: boolean | null;
  unsupported_paragraphs?: number[];
  fabricated_citations?: string[];
  /** paragraph_index (string key) → driving block_ids. Persisted server-side
   * (SECTION_DRAFT_GENERATED, SPR-09 M3) and returned so the X-ray can show
   * paragraph→blocks immediately; a reload reads the SAME map back from
   * GET /deliverables/{id}.prose_provenance. Empty unless status==generated. */
  prose_provenance?: Record<string, string[]>;
}

/** Generate a section's prose from its attached blocks (SPR-06). The live
 * model path may return 503 until creative_writer is wired into dispatch. */
export async function generateSection(sectionId: string): Promise<GenerationResult> {
  return _json<GenerationResult>(
    await apiFetch(`${API_BASE}/write/sections/${encodeURIComponent(sectionId)}/generate`, {
      method: "POST",
    }),
    "POST /write/sections/{id}/generate",
  );
}

export interface BrainstormEmitBody {
  section_id: string;
  deliverable_id?: string;
  insights: string[];
  questions: string[];
  data_points: string[];
}

export interface BrainstormEmitResult {
  block_ids: string[];
  insight_count: number;
  question_count: number;
  data_count: number;
  skipped_duplicates: number;
  flagged_unverified: string[];
}

/** Emit brainstorm drivers as user-originated OutlineBlocks (SPR-05).
 * Asserted data points are flagged unverified by the backend. */
export async function emitBrainstormBlocks(
  body: BrainstormEmitBody,
): Promise<BrainstormEmitResult> {
  return _json<BrainstormEmitResult>(
    await apiFetch(`${API_BASE}/write/brainstorm/emit-blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "POST /write/brainstorm/emit-blocks",
  );
}
