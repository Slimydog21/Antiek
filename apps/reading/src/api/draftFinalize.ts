/**
 * Pure TS finalize gate (mirrors substrate/twin_notes/finalize_gate.py #815).
 *
 * Offline authorization for provisional draft → parent mutation.
 * No network, no store writes. UI/callers must require authorized===true
 * before invoking any parent-mutating merge path.
 */

export interface FinalizeRequest {
  draft_id: string;
  parent_asset_id: string;
  provisional: boolean;
  operator_accepted: boolean;
  twin_ids?: string[];
  twin_parent_ids?: string[];
}

export interface FinalizeAuthorization {
  authorized: boolean;
  draft_id: string;
  parent_asset_id: string;
  reason: string;
  notes: string[];
}

export class FinalizeGateError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FinalizeGateError";
  }
}

/**
 * Authorize finalize of a provisional draft-merge artifact.
 * Returns authorized=false with honest reason on policy deny.
 * Throws FinalizeGateError on malformed empty ids.
 */
export function authorizeFinalize(req: FinalizeRequest): FinalizeAuthorization {
  const draft_id = (req.draft_id || "").trim();
  const parent_asset_id = (req.parent_asset_id || "").trim();
  if (!draft_id) {
    throw new FinalizeGateError("draft_id must be non-empty");
  }
  if (!parent_asset_id) {
    throw new FinalizeGateError("parent_asset_id must be non-empty");
  }

  if (req.provisional !== true) {
    return {
      authorized: false,
      draft_id,
      parent_asset_id,
      reason: "not_provisional_draft",
      notes: [
        "finalize gate only applies to provisional draft-merge artifacts",
        "non-provisional payloads must not be treated as draft-merge finalization",
      ],
    };
  }

  if (req.operator_accepted !== true) {
    return {
      authorized: false,
      draft_id,
      parent_asset_id,
      reason: "operator_accept_required",
      notes: [
        "explicit operator_accepted=true required before parent mutation",
      ],
    };
  }

  if (req.twin_parent_ids !== undefined) {
    const parents = [
      ...new Set(
        req.twin_parent_ids.map((p) => String(p).trim()).filter(Boolean),
      ),
    ];
    if (parents.length > 0 && !(parents.length === 1 && parents[0] === parent_asset_id)) {
      return {
        authorized: false,
        draft_id,
        parent_asset_id,
        reason: "cross_parent_twins",
        notes: [
          `finalize requires all twins to share parent_asset_id=${JSON.stringify(parent_asset_id)}`,
          `got parents=${parents.slice().sort().join(", ")}`,
        ],
      };
    }
  }

  if (req.twin_ids !== undefined && req.twin_ids.length === 0) {
    return {
      authorized: false,
      draft_id,
      parent_asset_id,
      reason: "no_twins",
      notes: ["finalize requires at least one twin when twin_ids is provided"],
    };
  }

  return {
    authorized: true,
    draft_id,
    parent_asset_id,
    reason: "ok",
    notes: [
      "authorized: provisional draft accepted by operator",
      "caller may proceed to parent-mutating merge (not performed here)",
    ],
  };
}

export function formatFinalizeReason(reason: string): string {
  switch (reason) {
    case "ok":
      return "authorized to finalize";
    case "not_provisional_draft":
      return "not a provisional draft";
    case "operator_accept_required":
      return "operator acceptance required";
    case "cross_parent_twins":
      return "cross-parent twins rejected";
    case "no_twins":
      return "no twins provided";
    default:
      return reason;
  }
}
