import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { EMPTY_SNAPSHOT } from "../../workspace/panel.types";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { EvidenceBundleWriteAction } from "./EvidenceBundleWriteAction";

const { acceptMock, applyMock, applyKnowledgeMock, authHarness, candidatesMock, createMock, executeMock, investigationsMock, listMock, previewAcceptMock, previewKnowledgeMock, previewMock, projectMock } = vi.hoisted(() => ({
  acceptMock: vi.fn(), applyMock: vi.fn(), authHarness: { generation: 1 }, createMock: vi.fn(), executeMock: vi.fn(),
  applyKnowledgeMock: vi.fn(), candidatesMock: vi.fn(), investigationsMock: vi.fn(),
  listMock: vi.fn(), previewAcceptMock: vi.fn(), previewKnowledgeMock: vi.fn(), previewMock: vi.fn(), projectMock: vi.fn(),
}));
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ sessionGeneration: authHarness.generation }) }));
vi.mock("../../lib/api", async (original) => {
  const actual = await original<typeof import("../../lib/api")>();
  return { ...actual, listPrivateWriteDocuments: listMock,
    previewPrivateWriteEvidenceBundle: previewMock,
    applyPrivateWriteEvidenceBundle: applyMock,
    projectEvidenceBundleSynthesis: projectMock,
    createEvidenceBundleSynthesisProposal: createMock,
    executeEvidenceBundleSynthesis: executeMock,
    listInvestigations: investigationsMock,
    listSynthesisKnowledgeCandidates: candidatesMock,
    previewSynthesisKnowledgeAdmission: previewKnowledgeMock,
    applySynthesisKnowledgeAdmission: applyKnowledgeMock,
    previewEvidenceSynthesisWriteAcceptance: previewAcceptMock,
    applyEvidenceSynthesisWriteAcceptance: acceptMock };
});
vi.mock("../../api/settings", () => ({ fetchRegisteredModels: vi.fn().mockResolvedValue({
  models: [{ provider_id: "openai", model_id: "gpt-test", enabled: true }], count: 1,
}) }));
const H1 = "1".repeat(64); const H2 = "2".repeat(64);
const evidence = ["a", "b"].map((value, index) => ({
  source_kind: "synthesis_claim" as const, source_asset_id: `research-${index}`,
  claim_id: `claim-${index}`, chunk_ids: [`chunk-${index}`],
  document_id: `document-${index}`, receipt_sha256: value.repeat(64),
}));

beforeEach(() => {
  authHarness.generation = 1; useWorkspace.setState({ ...EMPTY_SNAPSHOT });
  listMock.mockReset().mockResolvedValue({ documents: [{
    write_document_id: "ivwd-" + "c".repeat(32), project_id: "ivwp-" + "d".repeat(32),
    title: "Synthesis", revision: 3, html_sha256: H1, visibility: "private",
    updated_at: "now", origin_kind: "owner_native",
  }], next_after_document_id: null });
  previewMock.mockReset().mockResolvedValue({
    write_document_id: "ivwd-" + "c".repeat(32), project_id: "ivwp-" + "d".repeat(32),
    base_revision: 3, base_html_sha256: H1,
    proposed_html: "<article><section>Bundle</section></article>",
    proposed_html_sha256: H2, manifest_sha256: "3".repeat(64),
    preview_sha256: "4".repeat(64), items: [{}, {}], visibility: "private",
    origin_kind: "owner_native", operation: "evidence_bundle",
  });
  applyMock.mockReset().mockResolvedValue({
    event_id: "event", write_document_id: "ivwd-" + "c".repeat(32),
    project_id: "ivwp-" + "d".repeat(32), prior_revision: 3, revision: 4,
    html_sha256: H2, replayed: false, visibility: "private", operation: "evidence_bundle",
    bundle_id: "ivwb-" + "e".repeat(27),
  });
  projectMock.mockReset().mockResolvedValue({ source_kind: "evidence_bundle",
    bundle_id: "ivwb-" + "e".repeat(27), write_document_id: "ivwd-" + "c".repeat(32),
    project_id: "ivwp-" + "d".repeat(32), provider_id: "openai", model_id: "gpt-test",
    projected_max_cents: 25, expected_output_tokens: 4000, item_count: 2,
    budget: { daily_cap_usd: 10, spent_usd: 1, remaining_usd: 9, spent_status: "known", cap_env: "X", notes: [] },
    visibility: "private" });
  createMock.mockReset().mockResolvedValue({ proposal_id: "ivbp-1", source_kind: "evidence_bundle",
    bundle_id: "ivwb-" + "e".repeat(27), write_document_id: "ivwd-" + "c".repeat(32),
    project_id: "ivwp-" + "d".repeat(32), revision: 1, base_revision: 0,
    source_manifest_sha256: H1, source_content_sha256: H2, source_receipt_sha256: "3".repeat(64),
    provider_id: "openai", model_id: "gpt-test", projected_max_cents: 25,
    approved_ceiling_cents: 25, instruction: "Compare", state: "staged", item_count: 2, visibility: "private" });
  executeMock.mockReset().mockResolvedValue({ proposal_id: "ivbp-1", attempt_id: "attempt",
    run_id: "run", state: "ready_for_review", prompt_sha256: H1, route_sha256: H2,
    hold_id: "hold", actual_cents: 4, html: "<article>Review</article>", html_sha256: "3".repeat(64),
    rejection_reason: null, visibility: "private" });
  previewAcceptMock.mockReset().mockResolvedValue({ write_document_id: "ivwd-" + "c".repeat(32),
    project_id: "ivwp-" + "d".repeat(32), bundle_id: "ivwb-" + "e".repeat(27),
    proposal_id: "ivbp-1", execution_run_id: "run", base_revision: 4,
    base_html_sha256: H2, result_html_sha256: "3".repeat(64),
    proposed_html: "<article>Accepted preview</article>", proposed_html_sha256: "4".repeat(64),
    preview_sha256: "5".repeat(64), visibility: "private", origin_kind: "owner_native",
    operation: "synthesis_accept" });
  acceptMock.mockReset().mockResolvedValue({ acceptance_id: "ivwsa-1", event_id: "event-2",
    proposal_id: "ivbp-1", bundle_id: "ivwb-" + "e".repeat(27), execution_run_id: "run",
    write_document_id: "ivwd-" + "c".repeat(32), project_id: "ivwp-" + "d".repeat(32),
    prior_revision: 4, revision: 5, html_sha256: "4".repeat(64), receipt_sha256: "5".repeat(64),
    replayed: false, visibility: "private", origin_kind: "owner_native", operation: "synthesis_accept" });
  const knowledgeEvidence = [{ evidence_unit_id: "evidence-1", relationship: "supports",
    operator_label: null, citation_receipt_sha256: "6".repeat(64), source_asset_id: "asset",
    claim_id: "claim", source_document_id: "document", chunk_ids: ["chunk"],
    source_content_sha256: "7".repeat(64), excerpt_sha256: "8".repeat(64) }];
  const knowledgeItem = { ordinal: 0, unit_index: 0, kind: "insight", original_text_sha256: "9".repeat(64),
    admitted_text: "The contradiction remains unresolved.", admitted_text_sha256: "d".repeat(64),
    canonical_text: "the contradiction remains unresolved.", graph_node_id: "insight-1",
    disposition: "created", evidence_sha256: "e".repeat(64),
    item_receipt_sha256: "f".repeat(64), evidence: knowledgeEvidence };
  candidatesMock.mockReset().mockResolvedValue({ acceptance_id: "ivwsa-1", proposal_id: "ivbp-1",
    units: [{ unit_index: 0, text: "The contradiction remains unresolved.",
      original_text_sha256: "9".repeat(64), evidence: knowledgeEvidence }],
    epistemic_status: "model_proposed", verification: "unverified", visibility: "private" });
  investigationsMock.mockReset().mockResolvedValue({ count: 1, investigations: [{
    investigation_id: "research-one", question: "Research one", status: "completed",
    started_at: "now", completed_at: "now", cost_usd_total: 1, parent_investigation_id: null,
  }] });
  previewKnowledgeMock.mockReset().mockResolvedValue({ acceptance_id: "ivwsa-1",
    proposal_id: "ivbp-1", target_investigation_id: "research-one",
    target_investigation_digest: "a".repeat(64), item_manifest_sha256: "b".repeat(64),
    preview_sha256: "c".repeat(64), items: [knowledgeItem],
    epistemic_status: "model_proposed_operator_admitted", verification: "unverified", visibility: "private" });
  applyKnowledgeMock.mockReset().mockResolvedValue({ admission_id: "ivska-1",
    acceptance_id: "ivwsa-1", proposal_id: "ivbp-1", bundle_id: "ivwb-" + "e".repeat(27),
    write_document_id: "ivwd-" + "c".repeat(32), project_id: "ivwp-" + "d".repeat(32),
    target_investigation_id: "research-one", receipt_sha256: "1".repeat(64), replayed: false,
    items: [knowledgeItem],
    epistemic_status: "model_proposed_operator_admitted", verification: "unverified", visibility: "private" });
});

it("projects, stages, and explicitly executes once with route-bound receipts", async () => {
  render(<EvidenceBundleWriteAction evidence={evidence} />);
  fireEvent.click(screen.getByRole("button", { name: "Draft citations into manuscript" }));
  await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Preview bundle" }));
  await screen.findByTitle("Evidence bundle manuscript preview");
  fireEvent.click(screen.getByRole("button", { name: "Merge bundle as one revision" }));
  await screen.findByText("Synthesize evidence bundle");
  fireEvent.change(screen.getByLabelText("Synthesis instruction"), { target: { value: "Compare" } });
  const project = screen.getByRole("button", { name: "Project cost" });
  fireEvent.click(project); fireEvent.click(project);
  await waitFor(() => expect(projectMock).toHaveBeenCalledTimes(1));
  const stage = await screen.findByRole("button", { name: "Approve ceiling and stage proposal" });
  fireEvent.click(stage); fireEvent.click(stage);
  await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
  expect(screen.getByText(/Execution still requires explicit authorization/)).toBeTruthy();
  const execute = screen.getByRole("button", { name: "Execute staged proposal" });
  fireEvent.click(execute); fireEvent.click(execute);
  await waitFor(() => expect(executeMock).toHaveBeenCalledTimes(1));
  expect(await screen.findByTitle("Private evidence synthesis review")).toBeTruthy();
  const previewWrite = screen.getByRole("button", { name: "Preview in manuscript" });
  fireEvent.click(previewWrite); fireEvent.click(previewWrite);
  await waitFor(() => expect(previewAcceptMock).toHaveBeenCalledTimes(1));
  expect(await screen.findByTitle("Evidence synthesis manuscript preview")).toBeTruthy();
  const accept = screen.getByRole("button", { name: "Accept into revision 5" });
  fireEvent.click(accept); fireEvent.click(accept);
  await waitFor(() => expect(acceptMock).toHaveBeenCalledTimes(1));
  expect(await screen.findByText("Retain synthesis in the knowledge graph")).toBeTruthy();
  await waitFor(() => expect(candidatesMock).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByLabelText("Select synthesis unit 1"));
  const previewKnowledge = screen.getByRole("button", { name: "Preview knowledge admission" });
  fireEvent.click(previewKnowledge); fireEvent.click(previewKnowledge);
  await waitFor(() => expect(previewKnowledgeMock).toHaveBeenCalledTimes(1));
  expect(await screen.findByText(/new to this investigation/)).toBeTruthy();
  const admit = screen.getByRole("button", { name: "Admit 1 unverified unit(s)" });
  fireEvent.click(admit); fireEvent.click(admit);
  await waitFor(() => expect(applyKnowledgeMock).toHaveBeenCalledTimes(1));
  expect(await screen.findByText(/Units remain explicitly unverified/)).toBeTruthy();
});
afterEach(() => cleanup());

it("requires explicit relationships, previews, and merges the ordered bundle once", async () => {
  render(<EvidenceBundleWriteAction evidence={evidence} />);
  fireEvent.click(screen.getByRole("button", { name: "Draft citations into manuscript" }));
  await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByLabelText("Evidence 1 relationship"), { target: { value: "supports" } });
  fireEvent.change(screen.getByLabelText("Evidence 2 relationship"), { target: { value: "contradicts" } });
  fireEvent.change(screen.getByLabelText("Evidence 1 operator framing"), { target: { value: "Baseline" } });
  fireEvent.click(screen.getByRole("button", { name: "Preview bundle" }));
  await waitFor(() => expect(previewMock).toHaveBeenCalledWith(
    "ivwp-" + "d".repeat(32), "ivwd-" + "c".repeat(32),
    expect.objectContaining({ items: [
      expect.objectContaining({ relationship: "supports", operator_label: "Baseline" }),
      expect.objectContaining({ relationship: "contradicts" }),
    ] }), expect.any(AbortSignal),
  ));
  expect(await screen.findByTitle("Evidence bundle manuscript preview")).toBeTruthy();
  const merge = screen.getByRole("button", { name: "Merge bundle as one revision" });
  fireEvent.click(merge); fireEvent.click(merge);
  await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1));
  expect(await screen.findByText("Synthesize evidence bundle")).toBeTruthy();
  expect(useWorkspace.getState().panels[
    `PrivateWrite:ivwp-${"d".repeat(32)}:ivwd-${"c".repeat(32)}`
  ]).toBeTruthy();
});
