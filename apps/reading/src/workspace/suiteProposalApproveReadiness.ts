/**
 * Residual (aux): pure Antiek-bench suite proposal Approve/Reject CTA readiness.
 *
 * propose≠promote forever — approve only when a proposed proposal_id exists
 * and status is "proposed". auto_promoted must never be true for a promotable
 * proposal (if server claims auto_promoted, refuse operator promote honesty).
 *
 * Outside model-install thrash (aut–auw) · recursive bench quality flywheel.
 */

export type SuiteProposalApproveBlockReason =
  | "ok"
  | "no_proposal"
  | "no_proposal_id"
  | "not_proposed_status"
  | "auto_promoted_refused";

export type SuiteProposalApproveReadiness = {
  has_proposal: boolean;
  has_proposal_id: boolean;
  proposal_id: string;
  status: string;
  auto_promoted: boolean;
  approve_ready: boolean;
  reject_ready: boolean;
  block_reason: SuiteProposalApproveBlockReason;
  /** Doctrine constants — hard to vary. */
  propose_neq_promote: true;
  never_auto_promote: true;
  summary: string;
  approve_title: string;
  reject_title: string;
};

/**
 * Approve & promote / Reject proposal CTA readiness.
 * approve_ready === reject_ready (same gate; operator chooses direction).
 */
export function suiteProposalApproveReadiness(opts: {
  has_proposal?: boolean | null;
  proposal_id?: string | null;
  status?: string | null;
  auto_promoted?: boolean | null;
}): SuiteProposalApproveReadiness {
  const proposal_id = String(opts.proposal_id || "").trim();
  const status = String(opts.status || "").trim();
  const has_proposal_id = Boolean(proposal_id);
  const has_proposal =
    opts.has_proposal === true || has_proposal_id;
  const auto_promoted = opts.auto_promoted === true;

  let block_reason: SuiteProposalApproveBlockReason = "ok";
  if (auto_promoted) {
    block_reason = "auto_promoted_refused";
  } else if (!has_proposal) {
    block_reason = "no_proposal";
  } else if (!has_proposal_id) {
    block_reason = "no_proposal_id";
  } else if (status !== "proposed") {
    block_reason = "not_proposed_status";
  }

  const approve_ready = block_reason === "ok";
  const reject_ready = approve_ready;

  let summary: string;
  let approve_title: string;
  let reject_title: string;
  if (approve_ready) {
    summary = `gate ready · proposal ${proposal_id} status=proposed · explicit promote only (propose≠promote)`;
    approve_title =
      "Approve & promote this suite proposal (explicit · never auto-promote · propose≠promote)";
    reject_title =
      "Reject this suite proposal (explicit · active suite unchanged · propose≠promote)";
  } else if (block_reason === "auto_promoted_refused") {
    summary =
      "refused · auto_promoted=true violates propose≠promote (never auto-promote)";
    approve_title =
      "Refusing promote: proposal claims auto_promoted (propose≠promote forever)";
    reject_title = approve_title;
  } else if (block_reason === "no_proposal") {
    summary = "no suite proposal · refresh from recorded usage first";
    approve_title = "No suite proposal to approve";
    reject_title = "No suite proposal to reject";
  } else if (block_reason === "no_proposal_id") {
    summary = "proposal missing id · refresh suite proposal";
    approve_title = "No proposal_id to approve/reject";
    reject_title = approve_title;
  } else {
    summary = `status=${status || "(empty)"} · only status=proposed is gate-ready`;
    approve_title = `Proposal not in proposed status (${status || "empty"}) — cannot promote`;
    reject_title = approve_title;
  }

  return {
    has_proposal,
    has_proposal_id,
    proposal_id,
    status,
    auto_promoted,
    approve_ready,
    reject_ready,
    block_reason,
    propose_neq_promote: true,
    never_auto_promote: true,
    summary,
    approve_title,
    reject_title,
  };
}
