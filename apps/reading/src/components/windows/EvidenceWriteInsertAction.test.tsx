import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { EMPTY_SNAPSHOT } from "../../workspace/panel.types";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { EvidenceWriteInsertAction } from "./EvidenceWriteInsertAction";

const { applyMock, authHarness, listMock, previewMock } = vi.hoisted(() => ({
  applyMock: vi.fn(), authHarness: { generation: 1 }, listMock: vi.fn(), previewMock: vi.fn(),
}));

vi.mock("../../lib/auth", () => ({
  useAuth: () => ({ sessionGeneration: authHarness.generation }),
}));
vi.mock("../../lib/api", async (original) => {
  const actual = await original<typeof import("../../lib/api")>();
  return { ...actual, listPrivateWriteDocuments: listMock,
    previewPrivateWriteEvidenceInsertion: previewMock,
    applyPrivateWriteEvidenceInsertion: applyMock };
});

const H1 = "1".repeat(64); const H2 = "2".repeat(64); const H3 = "3".repeat(64);
const evidence = { source_kind: "synthesis_claim" as const, source_asset_id: "research-1",
  claim_id: "claim-1", chunk_ids: ["chunk-1"], document_id: "document-1",
  receipt_sha256: "a".repeat(64) };

beforeEach(() => {
  authHarness.generation = 1; useWorkspace.setState({ ...EMPTY_SNAPSHOT });
  listMock.mockReset().mockResolvedValue({ documents: [{ write_document_id: "ivwd-" + "b".repeat(32),
    project_id: "ivwp-" + "c".repeat(32), title: "Analysis", revision: 1,
    html_sha256: H1, visibility: "private", updated_at: "now", origin_kind: "owner_native" }],
    next_after_document_id: null });
  previewMock.mockReset().mockResolvedValue({ write_document_id: "ivwd-" + "b".repeat(32),
    project_id: "ivwp-" + "c".repeat(32), base_revision: 1, base_html_sha256: H1,
    proposed_html: "<article><blockquote>Evidence</blockquote></article>",
    proposed_html_sha256: H2, excerpt_sha256: H3, source_title: "Source",
    citation_receipt_sha256: evidence.receipt_sha256, preview_sha256: "4".repeat(64),
    visibility: "private", origin_kind: "owner_native" });
  applyMock.mockReset().mockResolvedValue({ event_id: "event-1",
    write_document_id: "ivwd-" + "b".repeat(32), project_id: "ivwp-" + "c".repeat(32),
    revision: 2, prior_revision: 1, html_sha256: H2, replayed: false,
    visibility: "private", operation: "evidence_insert" });
});
afterEach(() => cleanup());

it("previews server-owned evidence then inserts once and opens the stable desk", async () => {
  render(<EvidenceWriteInsertAction evidence={evidence} />);
  fireEvent.click(screen.getByRole("button", { name: "Insert evidence into manuscript" }));
  await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
  fireEvent.click(await screen.findByRole("button", { name: "Preview insertion" }));
  await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1));
  expect(await screen.findByTitle("Evidence insertion preview")).toBeTruthy();
  const insert = screen.getByRole("button", { name: "Insert as new revision" });
  fireEvent.click(insert); fireEvent.click(insert);
  await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(useWorkspace.getState().panels[
    `PrivateWrite:ivwp-${"c".repeat(32)}:ivwd-${"b".repeat(32)}`
  ]?.props).toEqual({ projectId: "ivwp-" + "c".repeat(32), writeDocumentId: "ivwd-" + "b".repeat(32) });
});
