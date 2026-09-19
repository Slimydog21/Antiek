import { API_BASE, ApiError, apiFetch } from "../lib/api";
import { isHtmlDocumentIdentifier } from "./htmlDocumentRefs";
import { parseDeepResearchSessionResumeRef } from "./deepResearchSessionRefs";

export type WorkspaceResumeEntry =
  | { kind: "stats" }
  | { kind: "library" }
  | { kind: "subaction"; workflow: "research" | "read" | "write" | "speak" }
  | { kind: "research_artifact"; investigation_id: string }
  | {
      kind: "hosted_html_document";
      resolver: "hosted_document" | "engagement_document";
      document_id: string;
    }
  | { kind: "deep_research_session"; session_id: string }
  | { kind: "collective_unit"; manifest_id: string }
  | { kind: "ancestry_interrogation"; investigation_id: string; manifest_id: string; receipt_id: string }
  | { kind: "collective_council"; plan_id: string };

export type WorkspaceCheckpoint = { schema_version: 1; revision: number; entries: WorkspaceResumeEntry[] };
export type WorkspaceReceipt = { status: "synced"; revision: number; event_id: string };

function exactObject(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("invalid workspace response");
  const object = value as Record<string, unknown>;
  const actual = Object.keys(object).sort();
  if (actual.length !== keys.length || actual.some((key, index) => key !== [...keys].sort()[index])) {
    throw new Error("invalid workspace response");
  }
  return object;
}

export function parseWorkspaceEntry(value: unknown): WorkspaceResumeEntry {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("invalid workspace entry");
  const kind = (value as Record<string, unknown>).kind;
  if (kind === "stats" || kind === "library") {
    exactObject(value, ["kind"]);
    return { kind };
  }
  if (kind === "subaction") {
    const object = exactObject(value, ["kind", "workflow"]);
    if (!["research", "read", "write", "speak"].includes(String(object.workflow))) throw new Error("invalid workspace entry");
    return { kind, workflow: object.workflow as "research" | "read" | "write" | "speak" };
  }
  if (kind === "research_artifact") {
    const object = exactObject(value, ["kind", "investigation_id"]);
    if (typeof object.investigation_id !== "string" || !object.investigation_id || object.investigation_id.length > 512) throw new Error("invalid workspace entry");
    return { kind, investigation_id: object.investigation_id };
  }
  if (kind === "hosted_html_document") {
    const object = exactObject(value, ["kind", "resolver", "document_id"]);
    if (
      (object.resolver !== "hosted_document" && object.resolver !== "engagement_document")
      || !isHtmlDocumentIdentifier(object.document_id)
    ) throw new Error("invalid workspace entry");
    return { kind, resolver: object.resolver, document_id: object.document_id };
  }
  if (kind === "deep_research_session") {
    const object = exactObject(value, ["kind", "session_id"]);
    const reference = parseDeepResearchSessionResumeRef({ session_id: object.session_id });
    if (!reference) throw new Error("invalid workspace entry");
    return { kind, session_id: reference.session_id };
  }
  if (kind === "collective_unit") {
    const object = exactObject(value, ["kind", "manifest_id"]);
    if (typeof object.manifest_id !== "string" || !object.manifest_id || object.manifest_id.length > 512) throw new Error("invalid workspace entry");
    return { kind, manifest_id: object.manifest_id };
  }
  if (kind === "ancestry_interrogation") {
    const object = exactObject(value, ["kind", "investigation_id", "manifest_id", "receipt_id"]);
    if (
      typeof object.investigation_id !== "string" || !object.investigation_id || object.investigation_id.length > 512
      || typeof object.manifest_id !== "string" || !object.manifest_id || object.manifest_id.length > 512
      || typeof object.receipt_id !== "string" || !object.receipt_id || object.receipt_id.length > 512
      || [object.investigation_id, object.manifest_id, object.receipt_id].some((item) => item !== item.trim() || /[\u0000-\u001f\u007f]/u.test(item))
    ) throw new Error("invalid workspace entry");
    return { kind, investigation_id: object.investigation_id, manifest_id: object.manifest_id, receipt_id: object.receipt_id };
  }
  if (kind === "collective_council") {
    const object = exactObject(value, ["kind", "plan_id"]);
    if (typeof object.plan_id !== "string" || !object.plan_id || object.plan_id.length > 512) throw new Error("invalid workspace entry");
    return { kind, plan_id: object.plan_id };
  }
  throw new Error("invalid workspace entry");
}

export function parseWorkspaceCheckpoint(value: unknown): WorkspaceCheckpoint {
  const object = exactObject(value, ["schema_version", "revision", "entries"]);
  if (object.schema_version !== 1 || !Number.isSafeInteger(object.revision) || Number(object.revision) < 0 || !Array.isArray(object.entries) || object.entries.length > 8) throw new Error("invalid workspace response");
  const entries = object.entries.map(parseWorkspaceEntry);
  if (new Set(entries.map((entry) => JSON.stringify(entry))).size !== entries.length) throw new Error("invalid workspace response");
  return { schema_version: 1, revision: Number(object.revision), entries };
}

function parseReceipt(value: unknown): WorkspaceReceipt {
  const object = exactObject(value, ["status", "revision", "event_id"]);
  if (object.status !== "synced" || !Number.isSafeInteger(object.revision) || Number(object.revision) < 1 || typeof object.event_id !== "string" || !object.event_id) throw new Error("invalid workspace receipt");
  return { status: "synced", revision: Number(object.revision), event_id: object.event_id };
}

async function json(response: Response): Promise<unknown> {
  if (!response.ok) throw new ApiError("workspace resume request failed", response.status, await response.text());
  return response.json();
}

export async function getWorkspaceResume(signal?: AbortSignal): Promise<WorkspaceCheckpoint> {
  return parseWorkspaceCheckpoint(await json(await apiFetch(`${API_BASE}/account/workspace-resume`, { signal, cache: "no-store" })));
}

export async function putWorkspaceResume(
  body: { schema_version: 1; base_revision: number; entries: WorkspaceResumeEntry[]; mutation_key: string },
  signal?: AbortSignal,
): Promise<WorkspaceReceipt> {
  return parseReceipt(await json(await apiFetch(`${API_BASE}/account/workspace-resume`, {
    method: "PUT", signal, cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })));
}
