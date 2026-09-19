import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ClaimSupportInspector from "./ClaimSupportInspector";
import {
  acceptEffectiveOwnerContext,
  acceptReasoningAncestryInterrogation,
  acceptRecursiveRoundContext,
  acceptClaimRevisionCompensation,
  acceptClaimRevision,
  createClaimReconsideration,
  getEffectiveClaimIterations,
  getReasoningAncestry,
  getResearchArtifactClaim,
  previewClaimReconsideration,
  previewClaimRevision,
  previewClaimRevisionCompensation,
  previewEffectiveOwnerContext,
  previewReasoningAncestryInterrogation,
  previewRecursiveRoundContext,
  reserveResearchArtifactClaimChallenge,
} from "../lib/api";
import { openHostedDocumentPanel } from "../workspace/actions";
import { openDeepResearchFromHighlight } from "../workspace/deepResearchWindow";
import { openWindow } from "./windows/openWindow";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  getResearchArtifactClaim: vi.fn(),
  previewClaimReconsideration: vi.fn(),
  createClaimReconsideration: vi.fn(),
  getEffectiveClaimIterations: vi.fn(),
  getReasoningAncestry: vi.fn(),
  previewClaimRevision: vi.fn(),
  acceptClaimRevision: vi.fn(),
  previewClaimRevisionCompensation: vi.fn(),
  acceptClaimRevisionCompensation: vi.fn(),
  previewEffectiveOwnerContext: vi.fn(),
  acceptEffectiveOwnerContext: vi.fn(),
  previewReasoningAncestryInterrogation: vi.fn(),
  acceptReasoningAncestryInterrogation: vi.fn(),
  previewRecursiveRoundContext: vi.fn(),
  acceptRecursiveRoundContext: vi.fn(),
  reserveResearchArtifactClaimChallenge: vi.fn(),
}));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ sessionGeneration: 1 }) }));
vi.mock("../workspace/actions", () => ({ openHostedDocumentPanel: vi.fn() }));
vi.mock("../workspace/deepResearchWindow", () => ({ openDeepResearchFromHighlight: vi.fn() }));
vi.mock("./windows/openWindow", () => ({ openWindow: vi.fn() }));

const getClaim = vi.mocked(getResearchArtifactClaim);
const getIterations = vi.mocked(getEffectiveClaimIterations);
const getAncestry = vi.mocked(getReasoningAncestry);
const openSource = vi.mocked(openHostedDocumentPanel);
const reserveChallenge = vi.mocked(reserveResearchArtifactClaimChallenge);
const previewReconsideration = vi.mocked(previewClaimReconsideration);
const createReconsideration = vi.mocked(createClaimReconsideration);
const previewRevision = vi.mocked(previewClaimRevision);
const acceptRevision = vi.mocked(acceptClaimRevision);
const previewCompensation = vi.mocked(previewClaimRevisionCompensation);
const acceptCompensation = vi.mocked(acceptClaimRevisionCompensation);
const previewOwnerContext = vi.mocked(previewEffectiveOwnerContext);
const acceptOwnerContext = vi.mocked(acceptEffectiveOwnerContext);
const previewInterrogation = vi.mocked(previewReasoningAncestryInterrogation);
const acceptInterrogation = vi.mocked(acceptReasoningAncestryInterrogation);
const previewRecursive = vi.mocked(previewRecursiveRoundContext);
const acceptRecursive = vi.mocked(acceptRecursiveRoundContext);
const openChallenge = vi.mocked(openDeepResearchFromHighlight);
const openCollective = vi.mocked(openWindow);

describe("ClaimSupportInspector", () => {
  beforeEach(() => {
    cleanup();
    getClaim.mockReset();
    getIterations.mockReset();
    getIterations.mockResolvedValue({
      investigation_id: "inv",
      claim_index: 0,
      artifact_content_hash: "d".repeat(64),
      current_effective_claim: "Current owner revision.",
      current_head_transition_sha256: "c".repeat(64),
      next_round_eligible: true,
      rounds: [],
    });
    getAncestry.mockReset();
    getAncestry.mockResolvedValue({
      investigation_id: "inv",
      claim_index: 0,
      artifact_content_hash: "d".repeat(64),
      current_effective_claim: "Current owner revision.",
      current_head_transition_sha256: "c".repeat(64),
      graph_sha256: "9".repeat(64),
      nodes: [],
    });
    openSource.mockReset();
    reserveChallenge.mockReset();
    previewOwnerContext.mockReset();
    acceptOwnerContext.mockReset();
    previewInterrogation.mockReset();
    acceptInterrogation.mockReset();
    previewRecursive.mockReset();
    acceptRecursive.mockReset();
    previewReconsideration.mockReset();
    createReconsideration.mockReset();
    previewRevision.mockReset();
    acceptRevision.mockReset();
    previewCompensation.mockReset();
    acceptCompensation.mockReset();
    openChallenge.mockReset();
    openCollective.mockReset();
  });

  it("keeps direct and inherited support distinct without inventing source navigation", async () => {
    getClaim.mockResolvedValue({
      claim_index: 0,
      claim: "A bounded claim",
      supporting_chunk_ids: ["chunk-direct"],
      supporting_path_indices: [2],
      inherited_support: [{
        unit_id: "unit-prior",
        qualification_state: "legacy_unqualified",
        source_investigation_id: null,
        supporting_leaf_investigation_id: "leaf-one",
      }],
      direct_evidence: [{
        source_kind: "synthesis_claim",
        source_asset_id: "inv",
        claim_id: `artifact-v2:${"a".repeat(64)}:0`,
        chunk_ids: ["chunk-direct"],
        document_id: "document-direct",
        receipt_sha256: "c".repeat(64),
      }],
      evaluation: {
        advisory: true,
        event_id: "evaluation-owner",
        scorer_id: "groundedness-nli-v1",
        backend: "nli",
        score: 0.7,
        supported: true,
        supported_threshold: 0.5,
        relation: "entailed",
      },
      reviews: [{
        schema_version: 1,
        status: "later_owner_accepted_counter_analysis",
        challenge_receipt_sha256: "d".repeat(64),
        acceptance_receipt_sha256: "e".repeat(64),
        reversal_receipt_sha256: null,
        session_id: "session-review",
        spawn_id: "spawn-review",
        candidate_sha256: "f".repeat(64),
        candidate_text: "Later counter-analysis, kept separate.",
        evaluation_event_id: "ground-review",
        evidence_receipt_sha256s: ["c".repeat(64)],
        grants_authority: false,
      }],
    });
    const interrogationResponse = {
      status: "candidate" as const,
      preview_sha256: "7".repeat(64),
      receipt: {
        receipt_id: "ancestry-interrogation-id",
        receipt_sha256: "6".repeat(64),
        artifact_content_hash: "d".repeat(64),
        head_transition_sha256: "c".repeat(64),
        selected_terminal_ordinals: [1], closure_ordinals: [1], ordered_spawn_ids: ["spawn-round-one"],
        question: "What survives?", collective_id: "collective-one",
        manifest_id: "manifest-one", membership_sha256: "5".repeat(64),
        archive_grounded: false as const, grants_authority: false as const,
        permits_provider_call: false as const, permits_spend: false as const,
        permits_graph_admission: false as const, permits_write: false as const,
        permits_benchmark_feedback: false as const, permits_publication: false as const,
      },
      manifest: {
        manifest_id: "manifest-one", collective_id: "collective-one",
        ordered_spawn_ids: ["spawn-round-one"], membership_sha256: "5".repeat(64),
        availability: "ready" as const, view_format: "html" as const,
      },
      stale: false,
    };
    previewInterrogation.mockResolvedValue(interrogationResponse);
    acceptInterrogation.mockResolvedValue({ ...interrogationResponse, status: "accepted" });
    getAncestry.mockResolvedValue({
      investigation_id: "inv",
      claim_index: 0,
      artifact_content_hash: "d".repeat(64),
      current_effective_claim: "Current owner revision.",
      current_head_transition_sha256: "c".repeat(64),
      graph_sha256: "9".repeat(64),
      nodes: [{
        ordinal: 1,
        transition_sha256: "c".repeat(64),
        session_id: "session-round-one",
        spawn_id: "spawn-round-one",
        candidate_sha256: "1".repeat(64),
        parent_ordinals: [],
        child_ordinals: [],
        inherited_questions: [],
        depth: 0,
        is_root: true,
        is_recombination: false,
        recursive_pack_receipt_sha256: null,
        recursive_context_pack: null,
        ancestry_sha256: "8".repeat(64),
        prior_html_url: `/research/inv/artifact/history/${"a".repeat(64)}`,
        result_html_url: `/research/inv/artifact/view?content_hash=${"d".repeat(64)}`,
        archive_grounded: false,
        grants_authority: false,
        permits_graph_admission: false,
        permits_write: false,
        permits_benchmark_feedback: false,
        permits_publication: false,
        permits_provider_call: false,
        permits_spend: false,
      }],
    });
    render(<ClaimSupportInspector investigationId="inv" claimIndex={0} contentHash={"a".repeat(64)} />);

    expect(await screen.findByText("A bounded claim")).toBeTruthy();
    expect(screen.getByText("Direct evidence")).toBeTruthy();
    expect(screen.getByText("Inherited knowledge dependencies")).toBeTruthy();
    expect(screen.getByText("legacy evidence — not source-qualified")).toBeTruthy();
    screen.getByRole("button", { name: "open source in canonical HTML" }).click();
    expect(openSource).toHaveBeenCalledWith({
      documentId: "document-direct",
      chunkIds: ["chunk-direct"],
      citationReceiptSha256: "c".repeat(64),
      title: "Claim evidence",
    });
    expect(screen.getByText("Owner-accepted later counter-analysis")).toBeTruthy();
    expect(screen.getAllByText("Later counter-analysis, kept separate.")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "open reviewed HTML overlay" }).getAttribute("href"))
      .toBe(`/research/inv/artifact/reviewed-view?content_hash=${"a".repeat(64)}#claim-review-0`);
    previewReconsideration.mockResolvedValue({
      status: "candidate",
      preview: { preview_sha256: "9".repeat(64), proposed_claim: "Reworded claim.", rationale: "Because.", html: "<section />" },
      proposal: null,
      view_format: "html",
    });
    createReconsideration.mockResolvedValue({
      status: "created",
      preview: null,
      proposal: { receipt_sha256: "8".repeat(64), proposed_claim: "Reworded claim.", rationale: "Because.", grants_authority: false },
      view_format: "html",
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.change(screen.getByLabelText("Proposed replacement wording"), { target: { value: "Reworded claim." } });
    fireEvent.change(screen.getByLabelText("Owner rationale"), { target: { value: "Because." } });
    fireEvent.click(screen.getByRole("button", { name: "preview exact proposal" }));
    await waitFor(() => expect(previewReconsideration).toHaveBeenCalledWith("inv", 0, expect.objectContaining({
      acceptance_receipt_sha256s: ["e".repeat(64)], proposed_claim: "Reworded claim.", rationale: "Because.",
    })));
    expect(await screen.findByLabelText("exact reconsideration preview")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Proposed replacement wording"), { target: { value: "Changed after preview." } });
    expect(screen.queryByRole("button", { name: "create immutable proposal" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Proposed replacement wording"), { target: { value: "Reworded claim." } });
    fireEvent.click(screen.getByRole("button", { name: "preview exact proposal" }));
    fireEvent.click(await screen.findByRole("button", { name: "create immutable proposal" }));
    await waitFor(() => expect(createReconsideration).toHaveBeenCalledWith("inv", 0, expect.objectContaining({
      preview_sha256: "9".repeat(64), mutation_key: `claim-reconsideration:${"9".repeat(64)}`,
    })));
    expect(getClaim).toHaveBeenCalledWith("inv", 0, "a".repeat(64));
  });

  it("does not fetch for an unbound legacy feed claim", () => {
    render(<ClaimSupportInspector investigationId="inv" claimId="old-claim" />);
    expect(screen.getByText("Claim support unavailable")).toBeTruthy();
    expect(getClaim).not.toHaveBeenCalled();
  });

  it("separates an accepted owner revision from archived terminal evidence", async () => {
    previewRecursive.mockResolvedValue({
      status: "candidate",
      reservation: null,
      preview: {
        receipt_sha256: "5".repeat(64), pack_sha256: "6".repeat(64),
        artifact_content_hash: "d".repeat(64), current_effective_claim: "Current owner revision.",
        current_head_transition_sha256: "c".repeat(64), selected_round_ordinals: [1],
        selected_transition_sha256s: ["c".repeat(64)], follow_up_questions: ["What remains uncertain?"],
        rows: [{}], pack_bytes: 321, view_mode: "floating", preview_sha256: "7".repeat(64),
        archive_grounded: false, grants_authority: false, permits_provider_call: false,
        permits_spend: false, permits_graph_admission: false, permits_twin_promotion: false,
        permits_write: false, permits_benchmark_feedback: false, permits_publication: false,
      },
    });
    getIterations.mockResolvedValue({
      investigation_id: "inv",
      claim_index: 0,
      artifact_content_hash: "d".repeat(64),
      current_effective_claim: "Current owner revision.",
      current_head_transition_sha256: "c".repeat(64),
      next_round_eligible: true,
      rounds: [{
        ordinal: 1,
        prior_artifact_content_hash: "a".repeat(64),
        result_artifact_content_hash: "d".repeat(64),
        claim_index: 0,
        archived_claim: "Archived terminal claim.",
        prior_effective_claim: "Earlier owner wording.",
        candidate_text: "Bounded research candidate.",
        candidate_sha256: "1".repeat(64),
        review_rationale: "The candidate warrants narrower wording.",
        proposed_claim: "Current owner revision.",
        replacement_claim: "Current owner revision.",
        context_receipt_sha256: "2".repeat(64),
        review_receipt_sha256: "3".repeat(64),
        proposal_receipt_sha256: "4".repeat(64),
        transition_sha256: "c".repeat(64),
        session_id: "session-round-one",
        spawn_id: "spawn-round-one",
        question: "What evidence warrants narrowing this claim?",
        purpose: "counter_analysis",
        model_id: "research-model",
        research_tier: "deep",
        prior_html_url: `/research/inv/artifact/history/${"a".repeat(64)}`,
        result_html_url: `/research/inv/artifact/view?content_hash=${"d".repeat(64)}`,
        result_is_current: true,
        archive_grounded: false,
        grants_authority: false,
        permits_graph_admission: false,
        permits_write: false,
        permits_benchmark_feedback: false,
        permits_publication: false,
        permits_provider_call: false,
        permits_spend: false,
      }],
    });
    getAncestry.mockResolvedValue({
      investigation_id: "inv", claim_index: 0,
      artifact_content_hash: "d".repeat(64),
      current_effective_claim: "Current owner revision.",
      current_head_transition_sha256: "c".repeat(64),
      graph_sha256: "9".repeat(64),
      nodes: [{
        ordinal: 1, transition_sha256: "c".repeat(64),
        session_id: "session-round-one", spawn_id: "spawn-round-one",
        candidate_sha256: "1".repeat(64), parent_ordinals: [], child_ordinals: [],
        inherited_questions: [], depth: 0, is_root: true, is_recombination: false,
        recursive_pack_receipt_sha256: null, recursive_context_pack: null,
        ancestry_sha256: "8".repeat(64),
        prior_html_url: `/research/inv/artifact/history/${"a".repeat(64)}`,
        result_html_url: `/research/inv/artifact/view?content_hash=${"d".repeat(64)}`,
        archive_grounded: false, grants_authority: false, permits_graph_admission: false,
        permits_write: false, permits_benchmark_feedback: false, permits_publication: false,
        permits_provider_call: false, permits_spend: false,
      }],
    });
    const ownerInterrogation = {
      status: "candidate", preview_sha256: "7".repeat(64), stale: false,
      receipt: {
        receipt_id: "ancestry-interrogation-id", receipt_sha256: "6".repeat(64),
        artifact_content_hash: "d".repeat(64), head_transition_sha256: "c".repeat(64),
        selected_terminal_ordinals: [1], closure_ordinals: [1], ordered_spawn_ids: ["spawn-round-one"], question: "What survives?",
        collective_id: "collective-one", manifest_id: "manifest-one", membership_sha256: "5".repeat(64),
        archive_grounded: false, grants_authority: false, permits_provider_call: false,
        permits_spend: false, permits_graph_admission: false, permits_write: false,
        permits_benchmark_feedback: false, permits_publication: false,
      },
      manifest: { manifest_id: "manifest-one", collective_id: "collective-one", ordered_spawn_ids: ["spawn-round-one"], membership_sha256: "5".repeat(64), availability: "ready", view_format: "html" },
    } satisfies Awaited<ReturnType<typeof previewReasoningAncestryInterrogation>>;
    previewInterrogation.mockResolvedValue(ownerInterrogation);
    acceptInterrogation.mockResolvedValue({ ...ownerInterrogation, status: "accepted" });
    getClaim.mockResolvedValue({
      claim_index: 0,
      claim: "Archived terminal claim.",
      supporting_chunk_ids: [],
      supporting_path_indices: [],
      inherited_support: [],
      direct_evidence: [],
      evaluation: {
        advisory: true,
        event_id: "evaluation-owner",
        scorer_id: "groundedness-nli-v1",
        backend: "nli",
        score: 0.7,
        supported: true,
        supported_threshold: 0.5,
        relation: "entailed",
      },
      reviews: [],
      reconsiderations: [],
      owner_revision: {
        status: "owner_accepted_claim_revision",
        prior_artifact_content_hash: "a".repeat(64),
        proposal_receipt_sha256: "b".repeat(64),
        transition_sha256: "c".repeat(64),
        revised_claim: "Current owner revision.",
        rationale: "Later accepted analysis narrowed the claim.",
        effective_claim: "Current owner revision.",
        head_transition_sha256: "c".repeat(64),
        compensations: [],
        archive_grounded: false,
        grants_authority: false,
      },
    });
    render(<ClaimSupportInspector investigationId="inv" claimIndex={0} contentHash={"d".repeat(64)} />);
    expect(await screen.findByText("Archived terminal claim.")).toBeTruthy();
    expect(screen.getAllByText("Current owner revision.").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "open immutable prior HTML" }).getAttribute("href"))
      .toBe(`/research/inv/artifact/history/${"a".repeat(64)}`);
    expect(screen.getByText(/not archive-grounded, model-verified/i)).toBeTruthy();
    expect(await screen.findByText("Recursive research ledger")).toBeTruthy();
    expect(screen.getByText(/Round 1: Earlier owner wording/)).toBeTruthy();
    expect(screen.getByText("Reasoning ancestry")).toBeTruthy();
    expect(screen.getByText(/Round 1 · depth 0 · root/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("select terminal branch 1 for collective interrogation"));
    fireEvent.change(screen.getByLabelText("Collective interrogation question"), { target: { value: "What survives?" } });
    fireEvent.click(screen.getByRole("button", { name: "preview collective interrogation" }));
    await waitFor(() => expect(previewInterrogation).toHaveBeenCalledWith("inv", 0, expect.objectContaining({
      content_hash: "d".repeat(64), selected_terminal_ordinals: [1], question: "What survives?",
    })));
    expect(await screen.findByText(/Exact closure 1 · manifest manifest-one/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "confirm and open collective" }));
    await waitFor(() => expect(acceptInterrogation).toHaveBeenCalledWith("inv", 0, expect.objectContaining({
      preview_sha256: "7".repeat(64), receipt_sha256: "6".repeat(64),
    })));
    expect(openCollective).toHaveBeenCalledWith(
      "collective_unit",
      {
        resume_ref: { manifest_id: "manifest-one" },
        interrogation_ref: { investigation_id: "inv", receipt_id: "ancestry-interrogation-id" },
      },
      expect.objectContaining({ mode: "floating" }),
    );
    fireEvent.click(screen.getByLabelText("include round 1 in recursive context"));
    fireEvent.change(screen.getByLabelText("Unresolved questions — one per line"), {
      target: { value: "What remains uncertain?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "preview exact recursive context" }));
    await waitFor(() => expect(previewRecursive).toHaveBeenCalledWith(
      "inv",
      0,
      expect.objectContaining({
        content_hash: "d".repeat(64),
        selected_round_ordinals: [1],
        follow_up_questions: ["What remains uncertain?"],
      }),
    ));
    expect(await screen.findByText(/321 bytes · 1 selected rounds/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Research current wording again" }));
    expect((screen.getByLabelText("Challenge goal") as HTMLTextAreaElement).value)
      .toMatch(/current owner wording again/i);
    previewOwnerContext.mockResolvedValue({
      status: "candidate",
      preview: {
        artifact_content_hash: "d".repeat(64),
        archived_claim: "Archived terminal claim.",
        effective_claim: "Current owner revision.",
        head_transition_sha256: "c".repeat(64),
        receipt_sha256: "7".repeat(64),
        preview_sha256: "8".repeat(64),
        revision_transition_sha256s: ["c".repeat(64)],
        archive_grounded: false,
        grants_authority: false,
        permits_provider_call: false,
        permits_spend: false,
        permits_graph_admission: false,
        permits_write: false,
        permits_benchmark_feedback: false,
        permits_publication: false,
      },
      reservation: null,
    });
    fireEvent.click(screen.getByRole("button", { name: "preview owner-claim research context" }));
    expect(await screen.findByText(/Selected owner-authored current wording/)).toBeTruthy();
    expect(screen.getByText(/no provider call or spend/i)).toBeTruthy();
    expect(reserveChallenge).not.toHaveBeenCalled();
    previewCompensation.mockResolvedValue({
      status: "candidate",
      preview: {
        operation: "restore_archived_terminal",
        prior_artifact_content_hash: "d".repeat(64),
        prospective_artifact_content_hash: "e".repeat(64),
        supersedes_transition_sha256: "c".repeat(64),
        prior_effective_claim: "Current owner revision.",
        replacement_claim: "Archived terminal claim.",
        rationale: "Restore while retaining history.",
        transition_sha256: "f".repeat(64),
        preview_sha256: "9".repeat(64),
        html: "<section />",
      },
      acceptance: null,
      view_format: "html",
    });
    acceptCompensation.mockResolvedValue({
      status: "accepted",
      preview: null,
      acceptance: {
        operation: "restore_archived_terminal",
        prior_artifact_content_hash: "d".repeat(64),
        artifact_content_hash: "e".repeat(64),
        supersedes_transition_sha256: "c".repeat(64),
        transition_sha256: "f".repeat(64),
        history_content_hash: "d".repeat(64),
        effective_owner_claim: "Archived terminal claim.",
        archive_grounded: false,
        grants_authority: false,
      },
      view_format: "html",
    });
    fireEvent.change(screen.getByLabelText("Compensation rationale"), { target: { value: "Restore while retaining history." } });
    fireEvent.click(screen.getByRole("button", { name: "preview compensating revision" }));
    fireEvent.click(await screen.findByRole("button", { name: "append compensating revision" }));
    await waitFor(() => expect(acceptCompensation).toHaveBeenCalledWith("inv", 0, expect.objectContaining({
      operation: "restore_archived_terminal", replacement_claim: null, preview_sha256: "9".repeat(64),
    })));
  });

  it("previews then explicitly accepts a canonical owner revision", async () => {
    const proposalClaim = {
      claim_index: 0,
      claim: "Archived terminal claim.",
      supporting_chunk_ids: [],
      supporting_path_indices: [],
      inherited_support: [],
      direct_evidence: [],
      evaluation: null,
      reviews: [],
      reconsiderations: [{
        schema_version: 1 as const,
        status: "owner_authored_reconsideration_proposal" as const,
        receipt_sha256: "b".repeat(64),
        selected_acceptance_receipt_sha256s: ["e".repeat(64)],
        proposed_claim: "Current owner revision.",
        rationale: "Because later analysis narrowed it.",
        grants_authority: false as const,
      }],
      owner_revision: null,
    };
    const revisedClaim = {
      ...proposalClaim,
      reconsiderations: [],
      owner_revision: {
        status: "owner_accepted_claim_revision" as const,
        prior_artifact_content_hash: "a".repeat(64),
        proposal_receipt_sha256: "b".repeat(64),
        transition_sha256: "c".repeat(64),
        revised_claim: "Current owner revision.",
        rationale: "Because later analysis narrowed it.",
        effective_claim: "Current owner revision.",
        head_transition_sha256: "c".repeat(64),
        compensations: [],
        archive_grounded: false as const,
        grants_authority: false as const,
      },
    };
    getClaim.mockResolvedValueOnce(proposalClaim).mockResolvedValueOnce(revisedClaim);
    previewRevision.mockResolvedValue({
      status: "candidate",
      preview: {
        prior_artifact_content_hash: "a".repeat(64),
        prospective_artifact_content_hash: "d".repeat(64),
        proposal_receipt_sha256: "b".repeat(64),
        transition_sha256: "c".repeat(64),
        preview_sha256: "f".repeat(64),
        original_claim: "Archived terminal claim.",
        revised_claim: "Current owner revision.",
        rationale: "Because later analysis narrowed it.",
        html: "<section />",
      },
      acceptance: null,
      view_format: "html",
    });
    acceptRevision.mockResolvedValue({
      status: "accepted",
      preview: null,
      acceptance: {
        prior_artifact_content_hash: "a".repeat(64),
        artifact_content_hash: "d".repeat(64),
        proposal_receipt_sha256: "b".repeat(64),
        transition_sha256: "c".repeat(64),
        history_content_hash: "a".repeat(64),
        archive_grounded: false,
        grants_authority: false,
      },
      view_format: "html",
    });
    render(<ClaimSupportInspector investigationId="inv" claimIndex={0} contentHash={"a".repeat(64)} />);
    fireEvent.click(await screen.findByRole("button", { name: "preview canonical revision" }));
    fireEvent.click(await screen.findByRole("button", { name: "accept as canonical owner revision" }));
    await waitFor(() => expect(acceptRevision).toHaveBeenCalledWith("inv", 0, expect.objectContaining({
      preview_sha256: "f".repeat(64), transition_sha256: "c".repeat(64),
    })));
    await waitFor(() => expect(getClaim).toHaveBeenLastCalledWith("inv", 0, "d".repeat(64)));
    expect((await screen.findAllByText("Current owner revision.")).length).toBeGreaterThan(0);
  });

  it("reserves an exact challenge and opens it as separate research", async () => {
    getClaim.mockResolvedValue({
      claim_index: 0,
      claim: "A challenged claim",
      supporting_chunk_ids: [],
      supporting_path_indices: [0],
      inherited_support: [],
      direct_evidence: [],
      evaluation: {
        advisory: true,
        event_id: "ground-1",
        scorer_id: "groundedness-nli-v1",
        backend: "nli",
        score: 0.1,
        supported: false,
        supported_threshold: 0.5,
        relation: "contradicted",
      },
    });
    reserveChallenge.mockResolvedValue({
      session_id: "session-1",
      spawn_id: "spawn-1",
      investigation_id: "child-1",
      parent_asset_id: "inv",
      selection_text: "A challenged claim",
      status: "reserved",
      view_mode: "floating",
      model_id: null,
      research_tier: "deep",
      view_format: "html",
      claim_challenge: {
        schema_version: 1,
        owner_account_digest: "e".repeat(64),
        source_asset_id: "inv",
        artifact_content_hash: "a".repeat(64),
        synthesis_event_id: "synth-1",
        claim_index: 0,
        claim_id: `artifact-v2:${"a".repeat(64)}:0`,
        claim_sha256: "b".repeat(64),
        evaluation_event_id: "ground-1",
        scorer_id: "groundedness-nli-v1",
        relation: "contradicted",
        score: 0.1,
        evidence_receipt_sha256s: [],
        model_id: null,
        research_tier: "deep",
        goal_sha256: "c".repeat(64),
        receipt_sha256: "d".repeat(64),
      },
    });
    render(<ClaimSupportInspector investigationId="inv" claimIndex={0} contentHash={"a".repeat(64)} />);
    fireEvent.click(await screen.findByRole("button", { name: "reserve separate challenge research" }));
    expect(reserveChallenge).toHaveBeenCalledWith("inv", 0, expect.objectContaining({
      content_hash: "a".repeat(64), research_tier: "deep", view_mode: "floating",
    }));
    await waitFor(() => expect(openChallenge).toHaveBeenCalledWith(expect.objectContaining({
      session_id: "session-1",
      selection_text: "A challenged claim",
      claim_challenge: expect.objectContaining({ evaluation_event_id: "ground-1" }),
    })));
    expect(screen.getByText(/makes no model call/i)).toBeTruthy();
  });
});
