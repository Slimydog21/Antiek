import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EffectiveContextReviewPanel } from "./EffectiveContextReviewPanel";
import {
  acceptEffectiveContextCompensation,
  acceptEffectiveContextReview,
  getEffectiveContextReview,
  previewEffectiveContextCompensation,
  previewEffectiveContextReview,
} from "../../lib/api";

vi.mock("../../lib/api", () => ({
  previewEffectiveContextCompensation: vi.fn(),
  acceptEffectiveContextCompensation: vi.fn(),
  previewEffectiveContextReview: vi.fn(),
  acceptEffectiveContextReview: vi.fn(),
  getEffectiveContextReview: vi.fn(),
}));

const preview = vi.mocked(previewEffectiveContextReview);
const accept = vi.mocked(acceptEffectiveContextReview);
const getReview = vi.mocked(getEffectiveContextReview);
const previewCompensation = vi.mocked(previewEffectiveContextCompensation);
const acceptCompensation = vi.mocked(acceptEffectiveContextCompensation);

const response = {
  status: "candidate" as const,
  preview: {
    artifact_content_hash: "a".repeat(64),
    claim_index: 0,
    context_receipt_sha256: "b".repeat(64),
    head_transition_sha256: "c".repeat(64),
    archived_claim: "Archived baseline.",
    effective_claim: "Current owner wording.",
    candidate_sha256: "d".repeat(64),
    candidate_text: "Candidate analysis.",
    archived_evaluation: {
      event_id: "evaluation",
      scorer_id: "nli",
      relation: "entailed" as const,
      score: 0.8,
    },
    archived_direct_evidence_receipt_sha256s: [],
    archived_inherited_support: [],
    disposition: "retain_current" as const,
    rationale: "Keep current wording.",
    proposed_claim: null,
    preview_sha256: "e".repeat(64),
    archive_grounded: false as const,
    grants_authority: false as const,
    permits_canonical_append: false as const,
  },
  acceptance: null,
  proposal: null,
};

describe("EffectiveContextReviewPanel", () => {
  it("previews three channels then accepts only a separate immutable review", async () => {
    getReview.mockRejectedValue(new Error("not accepted"));
    preview.mockResolvedValue(response);
    accept.mockResolvedValue({
      ...response,
      status: "accepted",
      acceptance: {
        receipt_sha256: "f".repeat(64),
        disposition: "retain_current",
        rationale: "Keep current wording.",
        permits_canonical_append: false,
        archive_grounded: false,
        grants_authority: false,
        permits_graph_admission: false,
        permits_write: false,
        permits_benchmark_feedback: false,
        permits_publication: false,
        permits_provider_call: false,
        permits_spend: false,
      },
      proposal: null,
    });
    render(
      <EffectiveContextReviewPanel
        investigationId="inv"
        sessionId="session"
        artifactContentHash={"a".repeat(64)}
      />,
    );
    fireEvent.change(screen.getByLabelText("Review rationale"), {
      target: { value: "Keep current wording." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview three-channel review" }));
    expect(await screen.findByText(/Archived baseline/)).toBeTruthy();
    expect(screen.getByText(/Current owner wording/)).toBeTruthy();
    expect(screen.getByText(/Candidate analysis/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Accept immutable review" }));
    await waitFor(() => expect(accept).toHaveBeenCalledWith("inv", "session", expect.objectContaining({
      disposition: "retain_current",
      preview_sha256: "e".repeat(64),
    })));
    expect(await screen.findByText(/Canonical owner wording remains unchanged/)).toBeTruthy();
  });

  it("requires a second exact preview before consuming a persisted proposal", async () => {
    getReview.mockResolvedValue({
      status: "accepted",
      archived_claim: "Archived baseline.",
      archived_evaluation: response.preview.archived_evaluation,
      archived_direct_evidence_receipt_sha256s: [],
      archived_inherited_support: [],
      effective_claim: "Current owner wording.",
      candidate_text: "Candidate analysis.",
      acceptance: {
        receipt_sha256: "f".repeat(64),
        disposition: "propose_compensation",
        rationale: "Narrow the wording.",
        permits_canonical_append: false,
        archive_grounded: false,
        grants_authority: false,
        permits_graph_admission: false,
        permits_write: false,
        permits_benchmark_feedback: false,
        permits_publication: false,
        permits_provider_call: false,
        permits_spend: false,
      },
      proposal: {
        receipt_sha256: "1".repeat(64),
        review_receipt_sha256: "f".repeat(64),
        proposed_claim: "Narrow owner wording.",
        rationale: "Narrow the wording.",
        permits_canonical_append: false,
        grants_authority: false,
      },
      consumption: null,
    });
    previewCompensation.mockResolvedValue({
      status: "candidate",
      preview: {
        prior_artifact_content_hash: "a".repeat(64),
        prospective_artifact_content_hash: "2".repeat(64),
        supersedes_transition_sha256: "c".repeat(64),
        prior_effective_claim: "Current owner wording.",
        replacement_claim: "Narrow owner wording.",
        rationale: "Narrow the wording.",
        transition_sha256: "3".repeat(64),
        preview_sha256: "4".repeat(64),
        source_context_receipt_sha256: "b".repeat(64),
        source_review_receipt_sha256: "f".repeat(64),
        source_proposal_receipt_sha256: "1".repeat(64),
      },
      acceptance: null,
    });
    acceptCompensation.mockResolvedValue({
      status: "accepted",
      preview: null,
      acceptance: {
        artifact_content_hash: "2".repeat(64),
        transition_sha256: "3".repeat(64),
        effective_owner_claim: "Narrow owner wording.",
        source_context_receipt_sha256: "b".repeat(64),
        source_review_receipt_sha256: "f".repeat(64),
        source_proposal_receipt_sha256: "1".repeat(64),
        archive_grounded: false,
        grants_authority: false,
      },
    });
    getReview.mockResolvedValueOnce(await getReview()).mockResolvedValueOnce({
      status: "accepted",
      archived_claim: "Archived baseline.",
      archived_evaluation: response.preview.archived_evaluation,
      archived_direct_evidence_receipt_sha256s: [],
      archived_inherited_support: [],
      effective_claim: "Narrow owner wording.",
      candidate_text: "Candidate analysis.",
      acceptance: {
        receipt_sha256: "f".repeat(64),
        disposition: "propose_compensation",
        rationale: "Narrow the wording.",
        permits_canonical_append: false,
        archive_grounded: false,
        grants_authority: false,
        permits_graph_admission: false,
        permits_write: false,
        permits_benchmark_feedback: false,
        permits_publication: false,
        permits_provider_call: false,
        permits_spend: false,
      },
      proposal: {
        receipt_sha256: "1".repeat(64),
        review_receipt_sha256: "f".repeat(64),
        proposed_claim: "Narrow owner wording.",
        rationale: "Narrow the wording.",
        permits_canonical_append: false,
        grants_authority: false,
      },
      consumption: {
        artifact_content_hash: "2".repeat(64),
        transition_sha256: "3".repeat(64),
        effective_owner_claim: "Narrow owner wording.",
        source_context_receipt_sha256: "b".repeat(64),
        source_review_receipt_sha256: "f".repeat(64),
        source_proposal_receipt_sha256: "1".repeat(64),
        archive_grounded: false,
        grants_authority: false,
      },
    });
    render(<EffectiveContextReviewPanel investigationId="inv" sessionId="session" artifactContentHash={"a".repeat(64)} />);
    fireEvent.click(await screen.findByRole("button", { name: "Preview canonical compensation" }));
    expect(await screen.findByText(/Prospective owner wording/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Accept canonical compensation" }));
    await waitFor(() => expect(acceptCompensation).toHaveBeenCalledWith("inv", "session", expect.objectContaining({
      proposal_receipt_sha256: "1".repeat(64),
      preview_sha256: "4".repeat(64),
      transition_sha256: "3".repeat(64),
    })));
    expect(await screen.findByText(/Canonical compensation accepted/)).toBeTruthy();
    expect(screen.getByText((_, element) => element?.textContent === "Owner-authored current wording: Narrow owner wording.")).toBeTruthy();
  });
});
