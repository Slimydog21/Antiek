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

export interface RepositoryHit {
  node_id: string;
  label: string;
  node_type: string;
  source_tier: number | null;
  document_id: string | null;
  document_title: string | null;
  score: number;
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

async function _json(resp: Response, what: string): Promise<unknown> {
  if (!resp.ok) {
    throw new ApiError(`${what} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
  return resp.json();
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function finiteNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed = finiteNumber(value);
  return parsed !== null && parsed >= 0 ? parsed : null;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  const parsed = finiteNumber(value);
  return parsed !== null && Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

function safeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = nonEmptyString(item);
    return text ? [text] : [];
  });
}

function safeNumberArray(value: unknown): number[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const number = nonNegativeSafeInteger(item);
    return number === null ? [] : [number];
  });
}

function safeRepositoryHit(value: unknown): RepositoryHit | null {
  const hit = record(value);
  if (!hit) return null;
  const nodeId = nonEmptyString(hit.node_id);
  const label = nonEmptyString(hit.label);
  if (!nodeId || !label) return null;
  return {
    node_id: nodeId,
    label,
    node_type: nonEmptyString(hit.node_type) ?? "insight",
    source_tier: finiteNonNegativeNumber(hit.source_tier),
    document_id: nullableString(hit.document_id),
    document_title: nullableString(hit.document_title),
    score: finiteNumber(hit.score) ?? 0,
  };
}

function safeRepositoryHits(value: unknown): RepositoryHit[] {
  const body = record(value);
  const hits = body?.hits;
  if (!Array.isArray(hits)) return [];
  return hits.flatMap((item) => {
    const hit = safeRepositoryHit(item);
    return hit ? [hit] : [];
  });
}

function safeFolder(value: unknown): FolderSummary | null {
  const folder = record(value);
  if (!folder) return null;
  const folderId = nonEmptyString(folder.folder_id);
  const name = nonEmptyString(folder.name);
  if (!folderId || !name) return null;
  return {
    folder_id: folderId,
    name,
    member_count: nonNegativeSafeInteger(folder.member_count) ?? 0,
  };
}

function safeFoldersResponse(value: unknown): FolderSummary[] {
  const body = record(value);
  const folders = body?.folders;
  if (!Array.isArray(folders)) return [];
  return folders.flatMap((item) => {
    const folder = safeFolder(item);
    return folder ? [folder] : [];
  });
}

function safeOutlineBlock(value: unknown): OutlineBlockView | null {
  const block = record(value);
  if (!block) return null;
  const outlineBlockId = nonEmptyString(block.outline_block_id);
  const sectionId = nonEmptyString(block.section_id);
  if (!outlineBlockId || !sectionId) return null;
  return {
    outline_block_id: outlineBlockId,
    section_id: sectionId,
    block_kind: nonEmptyString(block.block_kind) ?? "insight",
    provenance_kind: nonEmptyString(block.provenance_kind) ?? "graph_node",
    node_id: nullableString(block.node_id),
    content: nullableString(block.content),
    node_label: nullableString(block.node_label),
    block_index: nonNegativeSafeInteger(block.block_index) ?? 0,
    is_user_originated: block.is_user_originated === true,
  };
}

function safeSectionBlocksResponse(value: unknown): OutlineBlockView[] {
  const body = record(value);
  const blocks = body?.blocks;
  if (!Array.isArray(blocks)) return [];
  return blocks.flatMap((item) => {
    const block = safeOutlineBlock(item);
    return block ? [block] : [];
  });
}

function safeTraceTarget(value: unknown): TraceTarget {
  const target = record(value) ?? {};
  const fullTextAllowed = target.full_text_allowed === true;
  return {
    kind: nonEmptyString(target.kind) ?? "unknown",
    full_text_allowed: fullTextAllowed,
    document_id: fullTextAllowed ? nullableString(target.document_id) : null,
    document_title: fullTextAllowed ? nullableString(target.document_title) : null,
    chunk_ids: fullTextAllowed ? safeStringArray(target.chunk_ids) : [],
    primary_chunk_index: fullTextAllowed
      ? nonNegativeSafeInteger(target.primary_chunk_index)
      : null,
    primary_section_path: fullTextAllowed ? nullableString(target.primary_section_path) : null,
    servability_status: nullableString(target.servability_status),
    detail: nullableString(target.detail),
  };
}

function safePromoteResult(value: unknown): PromoteResult {
  const body = record(value);
  const deliverableId = body ? nonEmptyString(body.deliverable_id) : null;
  const sectionId = body ? nonEmptyString(body.section_id) : null;
  if (!deliverableId || !sectionId) {
    throw new Error("Malformed write promotion response.");
  }
  return {
    deliverable_id: deliverableId,
    section_id: sectionId,
    block_ids: safeStringArray(body?.block_ids),
  };
}

const GENERATION_STATUSES = new Set<GenerationResult["status"]>([
  "generated",
  "gap",
  "gate_failed",
  "invalid",
]);

function safeProseProvenance(value: unknown): Record<string, string[]> {
  const source = record(value);
  if (!source) return {};
  return Object.fromEntries(
    Object.entries(source).flatMap(([key, rawIds]) => {
      const paragraph = nonEmptyString(key);
      const ids = safeStringArray(rawIds);
      return paragraph && ids.length ? [[paragraph, ids]] : [];
    }),
  );
}

function safeGenerationResult(value: unknown, sectionId: string): GenerationResult {
  const body = record(value);
  const status =
    typeof body?.status === "string" &&
    GENERATION_STATUSES.has(body.status as GenerationResult["status"])
      ? (body.status as GenerationResult["status"])
      : "invalid";
  return {
    status,
    section_id: nonEmptyString(body?.section_id) ?? sectionId,
    prose_text: nonEmptyString(body?.prose_text) ?? undefined,
    detail: nonEmptyString(body?.detail) ?? undefined,
    gate_passed: typeof body?.gate_passed === "boolean" ? body.gate_passed : null,
    all_claims_cited:
      typeof body?.all_claims_cited === "boolean" ? body.all_claims_cited : null,
    unsupported_paragraphs: safeNumberArray(body?.unsupported_paragraphs),
    fabricated_citations: safeStringArray(body?.fabricated_citations),
    prose_provenance: safeProseProvenance(body?.prose_provenance),
  };
}

function safeBrainstormEmitResult(value: unknown): BrainstormEmitResult {
  const body = record(value);
  return {
    block_ids: safeStringArray(body?.block_ids),
    insight_count: nonNegativeSafeInteger(body?.insight_count) ?? 0,
    question_count: nonNegativeSafeInteger(body?.question_count) ?? 0,
    data_count: nonNegativeSafeInteger(body?.data_count) ?? 0,
    skipped_duplicates: nonNegativeSafeInteger(body?.skipped_duplicates) ?? 0,
    flagged_unverified: safeStringArray(body?.flagged_unverified),
  };
}

function assertNonNegativeSafeInteger(value: number, field: string): void {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new RangeError(`${field} must be a non-negative safe integer`);
  }
}

function assertPositiveSafeInteger(value: number, field: string): void {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new RangeError(`${field} must be a positive safe integer`);
  }
}

function requireNonEmptyString(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new TypeError(`${field} must be a non-empty string`);
  }
  const trimmed = value.trim();
  if (!trimmed) {
    throw new TypeError(`${field} must be a non-empty string`);
  }
  return trimmed;
}

function optionalRequestString(value: unknown): string | undefined {
  return nonEmptyString(value) ?? undefined;
}

function optionalRequestStringArray(value: unknown): string[] {
  return safeStringArray(value);
}

export async function searchRepository(opts: {
  q?: string;
  folderId?: string;
  sourceDocumentId?: string;
  limit?: number;
}): Promise<RepositoryHit[]> {
  const params = new URLSearchParams();
  const query = optionalRequestString(opts.q);
  const folderId = optionalRequestString(opts.folderId);
  const sourceDocumentId = optionalRequestString(opts.sourceDocumentId);
  if (query) params.set("q", query);
  if (folderId) params.set("folder_id", folderId);
  if (sourceDocumentId) params.set("source_document_id", sourceDocumentId);
  if (opts.limit !== undefined) {
    assertPositiveSafeInteger(opts.limit, "limit");
    params.set("limit", String(opts.limit));
  }
  const qs = params.toString();
  const body = await _json(
    await apiFetch(`${API_BASE}/write/blocks/search${qs ? `?${qs}` : ""}`),
    "GET /write/blocks/search",
  );
  return safeRepositoryHits(body);
}

export async function listFolders(): Promise<FolderSummary[]> {
  const body = await _json(
    await apiFetch(`${API_BASE}/write/folders`), "GET /write/folders",
  );
  return safeFoldersResponse(body);
}

export async function createFolder(name: string): Promise<string> {
  const folderName = requireNonEmptyString(name, "name");
  const body = record(await _json(
    await apiFetch(`${API_BASE}/write/folders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: folderName }),
    }),
    "POST /write/folders",
  ));
  return requireNonEmptyString(body?.folder_id, "folder_id");
}

export async function addFolderBlock(folderId: string, nodeId: string): Promise<void> {
  const resolvedFolderId = requireNonEmptyString(folderId, "folderId");
  const resolvedNodeId = requireNonEmptyString(nodeId, "nodeId");
  await _json(
    await apiFetch(`${API_BASE}/write/folders/${encodeURIComponent(resolvedFolderId)}/blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: resolvedNodeId }),
    }),
    "POST /write/folders/{id}/blocks",
  );
}

function sanitizedPlaceBlockBody(body: PlaceBlockBody): PlaceBlockBody {
  const base = {
    section_id: requireNonEmptyString(body.section_id, "section_id"),
    block_index: body.block_index,
    deliverable_id: optionalRequestString(body.deliverable_id),
  };
  if (body.provenance_kind === "graph_node") {
    return {
      ...base,
      block_kind: body.block_kind,
      provenance_kind: "graph_node",
      node_id: requireNonEmptyString(body.node_id, "node_id"),
    };
  }
  return {
    ...base,
    block_kind: body.block_kind,
    provenance_kind: "user_authored",
    content: requireNonEmptyString(body.content, "content"),
  };
}

/** Place a block in the outline (the drop target's commit). Returns the
 * new outline_block_id. */
export async function placeBlock(body: PlaceBlockBody): Promise<string> {
  assertNonNegativeSafeInteger(body.block_index, "block_index");
  const requestBody = sanitizedPlaceBlockBody(body);
  const r = record(await _json(
    await apiFetch(`${API_BASE}/write/blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    }),
    "POST /write/blocks",
  ));
  return requireNonEmptyString(r?.outline_block_id, "outline_block_id");
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
  const resolvedSectionId = requireNonEmptyString(sectionId, "sectionId");
  const body = await _json(
    await apiFetch(`${API_BASE}/write/sections/${encodeURIComponent(resolvedSectionId)}/blocks`),
    "GET /write/sections/{id}/blocks",
  );
  return safeSectionBlocksResponse(body);
}

/** Move/reorder a placed block within or across sections (drag-to-reorder). */
export async function moveBlock(
  outlineBlockId: string,
  toSectionId: string,
  toIndex: number,
): Promise<void> {
  const resolvedOutlineBlockId = requireNonEmptyString(outlineBlockId, "outlineBlockId");
  const resolvedToSectionId = requireNonEmptyString(toSectionId, "toSectionId");
  assertNonNegativeSafeInteger(toIndex, "to_index");
  await _json(
    await apiFetch(`${API_BASE}/write/blocks/${encodeURIComponent(resolvedOutlineBlockId)}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_section_id: resolvedToSectionId, to_index: toIndex }),
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
  /** Stable document-order locator for the first resolved chunk, not a Region. */
  primary_chunk_index: number | null;
  primary_section_path: string | null;
  servability_status: string | null;
  detail: string | null;
}

/** Resolve a placed block's trace target (the source the citation chip
 * opens). Honest about gating: `full_text_allowed=false` for a gated source
 * (§9.0 no-leak). Servable sources open in the live `/read/:documentId`
 * BookReader route; gated sources surface metadata/snippet only. */
export async function getTraceTarget(outlineBlockId: string): Promise<TraceTarget> {
  const resolvedOutlineBlockId = requireNonEmptyString(outlineBlockId, "outlineBlockId");
  return safeTraceTarget(await _json(
    await apiFetch(`${API_BASE}/write/blocks/${encodeURIComponent(resolvedOutlineBlockId)}/trace`),
    "GET /write/blocks/{id}/trace",
  ));
}

export interface PromoteResult {
  deliverable_id: string;
  section_id: string;
  block_ids: string[];
}

/** Promote a pre-outline context window to a structured outline (SPR-08). */
export async function promoteContext(body: unknown): Promise<PromoteResult> {
  return safePromoteResult(await _json(
    await apiFetch(`${API_BASE}/write/context/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "POST /write/context/promote",
  ));
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

/** Generate a section's prose from its attached blocks (SPR-06). The route is
 * wired through creative_writer; provider/credential failure still surfaces as
 * a clear 503 rather than fabricated prose. */
export async function generateSection(
  sectionId: string,
  opts: { paragraphIndex?: number } = {},
): Promise<GenerationResult> {
  const resolvedSectionId = requireNonEmptyString(sectionId, "sectionId");
  if (opts.paragraphIndex !== undefined) {
    assertNonNegativeSafeInteger(opts.paragraphIndex, "paragraph_index");
  }
  const body =
    opts.paragraphIndex === undefined
      ? undefined
      : JSON.stringify({ paragraph_index: opts.paragraphIndex });
  return safeGenerationResult(await _json(
    await apiFetch(`${API_BASE}/write/sections/${encodeURIComponent(resolvedSectionId)}/generate`, {
      method: "POST",
      ...(body
        ? {
            headers: { "Content-Type": "application/json" },
            body,
          }
        : {}),
    }),
    "POST /write/sections/{id}/generate",
  ), resolvedSectionId);
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
  const requestBody: BrainstormEmitBody = {
    section_id: requireNonEmptyString(body.section_id, "section_id"),
    insights: optionalRequestStringArray(body.insights),
    questions: optionalRequestStringArray(body.questions),
    data_points: optionalRequestStringArray(body.data_points),
  };
  const deliverableId = optionalRequestString(body.deliverable_id);
  if (deliverableId) requestBody.deliverable_id = deliverableId;
  return safeBrainstormEmitResult(await _json(
    await apiFetch(`${API_BASE}/write/brainstorm/emit-blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    }),
    "POST /write/brainstorm/emit-blocks",
  ));
}
