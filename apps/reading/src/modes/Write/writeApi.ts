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
  return r.outline_block_id;
}

export interface ReadToWriteHandoff {
  outline_block_id: string;
  node_id: string;
  deliverable_id: string;
  section_id: string;
  seam_event_id: string;
}

/** Commit a saved reader note into an outline without sending or copying its
 * text. The backend resolves note_id to the existing user-authored insight. */
export async function handoffReadNoteToWrite(body: {
  note_id: string;
  target_section_id: string;
  investigation_id: string;
}): Promise<ReadToWriteHandoff> {
  return _json<ReadToWriteHandoff>(
    await apiFetch(`${API_BASE}/write/read-handoffs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "POST /write/read-handoffs",
  );
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
const pendingMoveCommands = new Map<string, string>();

export async function moveBlock(
  outlineBlockId: string,
  toSectionId: string,
  toIndex: number,
): Promise<void> {
  const logicalMove = JSON.stringify([outlineBlockId, toSectionId, toIndex]);
  const commandId = pendingMoveCommands.get(logicalMove) ?? crypto.randomUUID();
  pendingMoveCommands.set(logicalMove, commandId);
  const send = () => apiFetch(
    `${API_BASE}/write/blocks/${encodeURIComponent(outlineBlockId)}/move`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": commandId,
      },
      body: JSON.stringify({ to_section_id: toSectionId, to_index: toIndex }),
    },
  );
  let response: Response;
  try {
    response = await send();
  } catch {
    response = await send();
  }
  if (response.status >= 500) response = await send();
  if (!response.ok && response.status < 500) pendingMoveCommands.delete(logicalMove);
  await _json<unknown>(response, "POST /write/blocks/{id}/move");
  pendingMoveCommands.delete(logicalMove);
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

export function traceReaderPath(
  target: TraceTarget,
  returnWriteId?: string | null,
): string | null {
  if (!target.full_text_allowed || !target.document_id) return null;
  const params = new URLSearchParams();
  const primaryChunk = target.chunk_ids[0]?.trim();
  if (primaryChunk) params.set("chunk", primaryChunk);
  const returnId = returnWriteId?.trim();
  if (returnId) params.set("return_write", returnId);
  const query = params.toString();
  return `/read/${encodeURIComponent(target.document_id)}${query ? `?${query}` : ""}`;
}

/** Read-only preview of a placed block's trace target. Product navigation uses
 * `handoffWriteBlockToRead` so the durable seam is committed before opening. */
export async function getTraceTarget(outlineBlockId: string): Promise<TraceTarget> {
  return _json<TraceTarget>(
    await apiFetch(`${API_BASE}/write/blocks/${encodeURIComponent(outlineBlockId)}/trace`),
    "GET /write/blocks/{id}/trace",
  );
}

const pendingReadHandoffs = new Map<string, string>();
const READ_HANDOFF_STORAGE_PREFIX = "antiek:write-to-read:";

function readHandoffCommand(logicalCommand: string): string | null {
  const inMemory = pendingReadHandoffs.get(logicalCommand);
  if (inMemory) return inMemory;
  try {
    return globalThis.localStorage?.getItem(
      `${READ_HANDOFF_STORAGE_PREFIX}${logicalCommand}`,
    ) ?? null;
  } catch {
    return null;
  }
}

function persistHandoffCommand(logicalCommand: string, commandId: string | null): void {
  if (commandId) pendingReadHandoffs.set(logicalCommand, commandId);
  else pendingReadHandoffs.delete(logicalCommand);
  try {
    const key = `${READ_HANDOFF_STORAGE_PREFIX}${logicalCommand}`;
    if (commandId) globalThis.localStorage?.setItem(key, commandId);
    else globalThis.localStorage?.removeItem(key);
  } catch {
    // Restricted storage still retains same-tab retry identity in memory.
  }
}

export async function handoffWriteBlockToRead(
  outlineBlockId: string,
  deliverableId: string,
): Promise<TraceTarget & { seam_event_id: string }> {
  const logicalCommand = JSON.stringify([outlineBlockId, deliverableId]);
  const commandId = readHandoffCommand(logicalCommand) ?? crypto.randomUUID();
  persistHandoffCommand(logicalCommand, commandId);
  const response = await apiFetch(
    `${API_BASE}/write/blocks/${encodeURIComponent(outlineBlockId)}/read-handoffs`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": commandId,
      },
      body: JSON.stringify({ deliverable_id: deliverableId }),
    },
  );
  const result = await _json<TraceTarget & { seam_event_id: string }>(
    response,
    "POST /write/blocks/{id}/read-handoffs",
  );
  persistHandoffCommand(logicalCommand, null);
  return result;
}

export interface SpeakCommission {
  question_node_id: string;
  section_id: string;
  speak_project_id: string;
  speak_path: string;
  seam_event_id: string;
}

const pendingSpeakCommissions = new Map<string, string>();
const inFlightSpeakCommissions = new Map<string, Promise<SpeakCommission>>();
const SPEAK_COMMISSION_STORAGE_PREFIX = "antiek:write-to-speak:";

function speakCommissionCommand(logicalCommand: string): string {
  const inMemory = pendingSpeakCommissions.get(logicalCommand);
  if (inMemory) return inMemory;
  try {
    const stored = globalThis.localStorage?.getItem(
      `${SPEAK_COMMISSION_STORAGE_PREFIX}${logicalCommand}`,
    );
    if (stored) return stored;
  } catch {
    // Same-tab memory retains retry identity when storage is restricted.
  }
  return crypto.randomUUID();
}

function persistSpeakCommission(logicalCommand: string, commandId: string | null): void {
  if (commandId) pendingSpeakCommissions.set(logicalCommand, commandId);
  else pendingSpeakCommissions.delete(logicalCommand);
  try {
    const key = `${SPEAK_COMMISSION_STORAGE_PREFIX}${logicalCommand}`;
    if (commandId) globalThis.localStorage?.setItem(key, commandId);
    else globalThis.localStorage?.removeItem(key);
  } catch {
    // The server receipt remains authoritative.
  }
}

async function executeSpeakCommission(
  outlineBlockId: string,
  deliverableId: string,
  logicalCommand: string,
): Promise<SpeakCommission> {
  const commandId = speakCommissionCommand(logicalCommand);
  persistSpeakCommission(logicalCommand, commandId);
  const response = await apiFetch(
    `${API_BASE}/write/blocks/${encodeURIComponent(outlineBlockId)}/speak-handoffs`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": commandId,
      },
      body: JSON.stringify({ deliverable_id: deliverableId }),
    },
  );
  try {
    const result = await _json<SpeakCommission>(
      response,
      "POST /write/blocks/{id}/speak-handoffs",
    );
    persistSpeakCommission(logicalCommand, null);
    return result;
  } catch (error) {
    if (response.status >= 400 && response.status < 500) {
      persistSpeakCommission(logicalCommand, null);
    }
    throw error;
  }
}

/** Commission one Speak project from the same question node, without copying it. */
export function commissionQuestionInterviews(
  outlineBlockId: string,
  deliverableId: string,
): Promise<SpeakCommission> {
  const logicalCommand = JSON.stringify([outlineBlockId, deliverableId]);
  const existing = inFlightSpeakCommissions.get(logicalCommand);
  if (existing) return existing;
  const request = executeSpeakCommission(
    outlineBlockId,
    deliverableId,
    logicalCommand,
  ).finally(() => inFlightSpeakCommissions.delete(logicalCommand));
  inFlightSpeakCommissions.set(logicalCommand, request);
  return request;
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
  status: "generated" | "gap" | "citation_failed" | "gate_failed" | "invalid";
  section_id: string;
  prose_text?: string;
  detail?: string;
  gate_passed?: boolean | null;
  all_claims_cited?: boolean | null;
  unsupported_paragraphs?: number[];
  fabricated_citations?: string[];
  provenance_mismatches?: number[];
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
