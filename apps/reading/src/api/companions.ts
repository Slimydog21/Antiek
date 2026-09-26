/**
 * companions.ts — the companion + evidence-base client (companions SPR-02).
 *
 * GET /documents/{id}/companion?format=json — the STRUCTURED payload the
 * rail renders (the sanctioned path: structured content, never generated
 * HTML injected into the DOM). GET /documents/{id}/evidence
 * — the inspect/debug dump's rows. Both owner-scoped server-side; a failed
 * or malformed read degrades to the honest empty state, never a crash.
 */
import { API_BASE, ApiError, apiFetch } from "../lib/api";

export interface CompanionClaim {
  evidence_id: string;
  kind: string;
  node_ref: string;
  /** null on a withheld source — the metadata line is all that's lawful. */
  text: string | null;
}

export interface CompanionAnchor {
  evidence_id: string;
  anchor_ref: string;
  status: string;
  page_index_hint: number | null;
}

export interface CompanionProcess {
  evidence_id: string;
  detail: string;
  label: string;
  status_line: string;
}

export interface CompanionPayload {
  document_id: string;
  exists: boolean;
  title: string | null;
  servable: boolean;
  rebuilt_at: string;
  claims: CompanionClaim[];
  anchors: CompanionAnchor[];
  processes: CompanionProcess[];
}

export interface EvidenceRowItem {
  evidence_id: string;
  kind: string;
  refs: string[];
  tombstone: boolean;
  rebuilt_at: string;
}

export async function getDocumentCompanion(documentId: string): Promise<CompanionPayload> {
  const resp = await apiFetch(
    `${API_BASE}/documents/${encodeURIComponent(documentId)}/companion?format=json`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /documents/{id}/companion failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  const raw = (await resp.json()) as Partial<CompanionPayload>;
  // Boundary validation: a malformed body is an honest unavailable, never a
  // crash rendering a non-payload.
  if (!Array.isArray(raw.claims) || !Array.isArray(raw.processes)) {
    throw new ApiError("companion: malformed payload", 0, JSON.stringify(raw));
  }
  return raw as CompanionPayload;
}

export async function listDocumentEvidence(
  documentId: string,
): Promise<{ rows: EvidenceRowItem[]; count: number }> {
  const resp = await apiFetch(
    `${API_BASE}/documents/${encodeURIComponent(documentId)}/evidence`,
  );
  if (!resp.ok) {
    throw new ApiError(
      `GET /documents/{id}/evidence failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  const raw = (await resp.json()) as { rows?: unknown };
  if (!Array.isArray(raw.rows)) {
    throw new ApiError("evidence: malformed payload", 0, JSON.stringify(raw));
  }
  return { rows: raw.rows as EvidenceRowItem[], count: raw.rows.length };
}
