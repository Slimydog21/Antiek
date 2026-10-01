/**
 * forkMerge.ts — the SPR-02 fork-merge client (thread-merge + document fork
 * SPR-03). The composed evidence view's ONLY mutation path: preview (no
 * writes, the receipt is the contract) then commit (bound to the preview,
 * multi-ack, per-conflict resolutions). Both calls are boundary-validated —
 * a malformed receipt throws, never a half-rendered merge.
 */
import { API_BASE, ApiError, apiFetch } from "../lib/api";

export interface ForkMergeItemRef {
  investigation_id: string;
  node_id: string;
}

export interface ForkMergeItem extends ForkMergeItemRef {
  kind: string;
  text: string;
  text_sha256: string;
  source_document_id: string | null;
}

export interface ForkMergeConflict {
  conflict_id: string;
  /** "cross_member_pair" | "anchor_passage" | "operator_flag". */
  kind: string;
  item_refs: ForkMergeItemRef[];
  detail: string;
  anchor_id: string | null;
  /** The pinned passage's quote — the picker's fork side (null when the
   *  pin was withheld). */
  anchor_quote: string | null;
}

export interface ForkMergePreview {
  status: string;
  merge_id: string;
  fork_id: string;
  fork_document_id: string;
  items: ForkMergeItem[];
  conflicts: ForkMergeConflict[];
  before_fork_hash: string;
  after_fork_hash: string;
  fork_bytes_before: number;
  fork_bytes_after: number;
  writes_performed: boolean;
}

export interface ForkMergeCommit extends ForkMergePreview {
  commit_id: string;
  event_id: string | null;
  /** item ref key → choice, as committed. */
  resolutions: Record<string, string>;
}

export interface ForkMergeResolution extends ForkMergeItemRef {
  choice: "accept" | "keep_fork" | "skip";
}

function isRef(raw: unknown): raw is ForkMergeItemRef {
  const r = raw as Partial<ForkMergeItemRef> | null;
  return (
    r !== null &&
    typeof r === "object" &&
    typeof r.investigation_id === "string" &&
    typeof r.node_id === "string"
  );
}

function isSha256(value: unknown): boolean {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function parsePreview(raw: unknown): ForkMergePreview {
  const r = raw as Partial<ForkMergePreview> | null;
  if (
    r === null ||
    typeof r !== "object" ||
    typeof r.merge_id !== "string" ||
    typeof r.fork_id !== "string" ||
    typeof r.fork_document_id !== "string" ||
    !Array.isArray(r.items) ||
    !Array.isArray(r.conflicts) ||
    !isSha256(r.before_fork_hash) ||
    !isSha256(r.after_fork_hash) ||
    typeof r.writes_performed !== "boolean"
  ) {
    throw new ApiError("fork-merge: malformed receipt", 0, JSON.stringify(raw));
  }
  for (const item of r.items) {
    if (!isRef(item) || typeof item.text !== "string" || typeof item.kind !== "string") {
      throw new ApiError("fork-merge: malformed item", 0, JSON.stringify(raw));
    }
  }
  for (const conflict of r.conflicts) {
    if (
      typeof conflict?.conflict_id !== "string" ||
      typeof conflict.kind !== "string" ||
      !Array.isArray(conflict.item_refs) ||
      !conflict.item_refs.every(isRef)
    ) {
      throw new ApiError("fork-merge: malformed conflict", 0, JSON.stringify(raw));
    }
  }
  return r as ForkMergePreview;
}

async function throwUnlessOk(resp: Response, label: string): Promise<void> {
  if (!resp.ok) {
    throw new ApiError(`${label} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
}

/** Preview the merge — no writes. 404 fork unknown; 422 an item ref that
 *  doesn't resolve to a distilled outcome of its thread. */
export async function previewForkMerge(body: {
  fork_id: string;
  items: ForkMergeItemRef[];
  flagged_conflicts?: ForkMergeItemRef[];
}): Promise<ForkMergePreview> {
  const resp = await apiFetch(`${API_BASE}/research/artifacts/fork-merge/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flagged_conflicts: [], ...body }),
  });
  await throwUnlessOk(resp, "POST /research/artifacts/fork-merge/preview");
  return parsePreview(await resp.json());
}

/** Commit a bound, reviewed preview. The caller sets BOTH acknowledgements
 *  from real operator controls and passes a resolution for every conflicted
 *  item — the server refuses (409) otherwise. */
export async function commitForkMerge(body: {
  fork_id: string;
  items: ForkMergeItemRef[];
  flagged_conflicts?: ForkMergeItemRef[];
  expected_merge_id: string;
  expected_before_fork_hash: string;
  resolutions: ForkMergeResolution[];
  acknowledge_fork_document_mutation: boolean;
  acknowledge_conflicts: boolean;
  operator_reviewer?: string;
}): Promise<ForkMergeCommit> {
  const resp = await apiFetch(`${API_BASE}/research/artifacts/fork-merge/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flagged_conflicts: [], ...body }),
  });
  await throwUnlessOk(resp, "POST /research/artifacts/fork-merge/commit");
  const raw = (await resp.json()) as Partial<ForkMergeCommit>;
  if (typeof raw?.commit_id !== "string" || typeof raw.resolutions !== "object") {
    throw new ApiError("fork-merge: malformed commit receipt", 0, JSON.stringify(raw));
  }
  return raw as ForkMergeCommit;
}
