/**
 * companions.ts — the companion + evidence-base client (companions SPR-02).
 *
 * GET /documents/{id}/companion?format=json — reads the LAST BUILD, never
 * writes. The answer is a discriminated union on `state`:
 *   built     — the structured payload the rail renders (the sanctioned path:
 *               structured content, never generated HTML injected into the DOM);
 *   not_built — nothing built yet for this owner;
 *   withheld  — built, but the document is now taken down or not servable; no
 *               content travels.
 * A payload with NO `state` (the pre-hotfix server, which rebuilt on every
 * read) is `built` when it otherwise validates, so the client works against
 * both servers.
 *
 * POST /documents/{id}/companion/refresh — the explicit rebuild (the only
 * write). A 503 carries whether a last build exists; that boolean is ALL the
 * rail may act on — no status number, server code or error_type is surfaced
 * for rendering.
 *
 * A foreign or missing document is a 404 on both routes (identical, never
 * disclosing existence). GET /documents/{id}/evidence — the inspect/debug
 * dump's rows. All owner-scoped server-side.
 */
import { API_BASE, ApiError, apiFetch } from "../lib/api";

/**
 * The claim row's kind. The server sends the grounded graph node's type —
 * `insight` or `question` (substrate/companions/projector.py). `claim` and
 * `evidence` are the evidence-index kinds, labelled if they ever arrive here;
 * any other string renders with no label.
 */
export type CompanionClaimKind = "insight" | "question" | "claim" | "evidence" | (string & {});

export interface CompanionClaim {
  evidence_id: string;
  kind: CompanionClaimKind;
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

export type BuiltCompanion = CompanionPayload & { state: "built" };

export interface NotBuiltCompanion {
  document_id: string;
  state: "not_built";
}

export type CompanionWithheldReason = "taken_down" | "not_servable";

export interface WithheldCompanion {
  document_id: string;
  state: "withheld";
  reason: CompanionWithheldReason;
}

export type CompanionResponse = BuiltCompanion | NotBuiltCompanion | WithheldCompanion;

export interface EvidenceRowItem {
  evidence_id: string;
  kind: string;
  refs: string[];
  tombstone: boolean;
  rebuilt_at: string;
}

/**
 * The refresh route's 503: the rebuild failed. `hasLastBuild` says whether the
 * server still holds a previous build (parsed from `has_last_build`; null when
 * that fact is unknown). The message deliberately names neither the server
 * code nor the error_type.
 */
export class CompanionRebuildFailedError extends ApiError {
  readonly hasLastBuild: boolean | null;

  constructor(body: string) {
    super("companion rebuild failed", 503, body);
    this.name = "CompanionRebuildFailedError";
    this.hasLastBuild = parseHasLastBuild(body);
  }
}

/** True for the 404 both routes answer for a foreign or missing document. */
export function isCompanionNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}

function companionUrl(documentId: string, suffix = ""): string {
  return `${API_BASE}/documents/${encodeURIComponent(documentId)}/companion${suffix}?format=json`;
}

function parseHasLastBuild(body: string): boolean | null {
  try {
    const parsed: unknown = JSON.parse(body);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      "has_last_build" in parsed &&
      typeof parsed.has_last_build === "boolean"
    ) {
      return parsed.has_last_build;
    }
  } catch {
    // An invalid error response tells us nothing about the saved build.
  }
  return null;
}

function malformed(raw: unknown): ApiError {
  return new ApiError("companion: malformed payload", 0, JSON.stringify(raw));
}

/**
 * Boundary validation: every answer is one of the three states, or it is
 * rejected (an honest failure, never a crash rendering a non-payload).
 */
export function parseCompanionResponse(raw: unknown): CompanionResponse {
  if (typeof raw !== "object" || raw === null) throw malformed(raw);
  const body = raw as Record<string, unknown>;
  const documentId = typeof body.document_id === "string" ? body.document_id : "";
  switch (body.state) {
    case "not_built":
      return { document_id: documentId, state: "not_built" };
    case "withheld":
      if (body.reason !== "taken_down" && body.reason !== "not_servable") throw malformed(raw);
      return {
        document_id: documentId,
        state: "withheld",
        reason: body.reason,
      };
    case "built":
    case undefined: {
      if (
        !Array.isArray(body.claims) ||
        !Array.isArray(body.processes) ||
        typeof body.rebuilt_at !== "string"
      ) {
        throw malformed(raw);
      }
      return {
        ...(body as unknown as CompanionPayload),
        anchors: Array.isArray(body.anchors) ? (body.anchors as CompanionAnchor[]) : [],
        state: "built",
      };
    }
    default:
      throw malformed(raw);
  }
}

export async function getDocumentCompanion(documentId: string): Promise<CompanionResponse> {
  const resp = await apiFetch(companionUrl(documentId));
  if (!resp.ok) {
    throw new ApiError(
      `GET /documents/{id}/companion failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return parseCompanionResponse(await resp.json());
}

/**
 * Rebuild the companion. Success is the built payload. A `withheld` answer is
 * passed through rather than rejected, so a takedown landing between the read
 * and the rebuild drops the content instead of leaving a stale copy on screen.
 * `?format=json` is sent so the structured payload comes back whichever way
 * the route defaults.
 */
export async function refreshDocumentCompanion(documentId: string): Promise<CompanionResponse> {
  const resp = await apiFetch(companionUrl(documentId, "/refresh"), { method: "POST" });
  if (resp.status === 503) {
    throw new CompanionRebuildFailedError(await resp.text());
  }
  if (!resp.ok) {
    throw new ApiError(
      `POST /documents/{id}/companion/refresh failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  return parseCompanionResponse(await resp.json());
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
