/**
 * Deep Research reading-surface API client (DRW SPR-10 transport → UI).
 *
 * Mirrors `interfaces/research/api/reading_routes.py` (prefix `/reading`).
 * Document raw_text + versions, content-anchored notes, living-note
 * challenge, and document-scoped structural gaps. Spin-research reuses the
 * `/research` cascade client (see `./research`), so there is no spin endpoint
 * here — the surface seeds a plan from a span/note/gap.
 */

import { API_BASE, ApiError, apiFetch } from "../lib/api";

export interface DocumentVersionRef {
  document_id: string;
  version: number;
  parent_document_id: string | null;
}

export interface ReadingDocument {
  document_id: string;
  title: string | null;
  raw_text: string | null;
  document_type: string;
  content_class: string | null;
  versions: DocumentVersionRef[];
}

export type NoteKind = "insight" | "question";

export interface DocumentNote {
  node_id: string;
  kind: NoteKind;
  text: string;
  confidence: string;
  /** Source-chunk texts to locate in raw_text by whitespace-normalized
   * content match (see ./modes/DeepResearchReading/anchor). */
  anchors: string[];
}

export interface DocumentGap {
  gap_id: string;
  kind: string;
  question: string;
  impact_score: number;
  backing_node_ids: string[];
}

export interface ChallengeResult {
  node_id: string;
  applied: boolean;
  new_text: string | null;
  escalated: boolean;
  escalated_question_id: string | null;
  reserved_child_investigation_id: string | null;
}

async function jsonOrThrow<T>(resp: Response, what: string): Promise<T> {
  if (!resp.ok) throw new ApiError(`${what} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json() as Promise<T>;
}

function get<T>(path: string): Promise<T> {
  return apiFetch(`${API_BASE}${path}`).then((r) => jsonOrThrow<T>(r, `GET ${path}`));
}
function post<T>(path: string, body: unknown): Promise<T> {
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).then((r) => jsonOrThrow<T>(r, `POST ${path}`));
}

export function getDocument(documentId: string): Promise<ReadingDocument> {
  return get(`/reading/documents/${encodeURIComponent(documentId)}`);
}

export function createDocumentVersion(documentId: string, newText: string): Promise<{
  document_id: string; new_document_id: string; unchanged: boolean;
}> {
  return post(`/reading/documents/${encodeURIComponent(documentId)}/versions`, { new_text: newText });
}

export function getDocumentNotes(documentId: string): Promise<{ document_id: string; notes: DocumentNote[] }> {
  return get(`/reading/documents/${encodeURIComponent(documentId)}/notes`);
}

export function getDocumentGaps(documentId: string): Promise<{ document_id: string; gaps: DocumentGap[] }> {
  return get(`/reading/documents/${encodeURIComponent(documentId)}/gaps`);
}

export function challengeNote(nodeId: string, req: {
  challenge_text: string; document_id: string; resolution?: string;
}): Promise<ChallengeResult> {
  return post(`/reading/notes/${encodeURIComponent(nodeId)}/challenge`, req);
}
