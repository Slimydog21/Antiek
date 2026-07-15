import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TwinNoteMergeWorkspace, { mergePreviewUrl } from "./TwinNoteMergeWorkspace";

const mocks = vi.hoisted(() => ({
  context: vi.fn(), bridge: vi.fn(), draft: vi.fn(), review: vi.fn(), apply: vi.fn(),
}));

vi.mock("../../api/research", () => ({
  getTwinNoteMergeContext: (...args: unknown[]) => mocks.context(...args),
  createTwinNoteMergeProjection: (...args: unknown[]) => mocks.bridge(...args),
  createDerivedMergeDraft: (...args: unknown[]) => mocks.draft(...args),
  createDerivedMergeReview: (...args: unknown[]) => mocks.review(...args),
  applyDerivedMergeReview: (...args: unknown[]) => mocks.apply(...args),
}));

const sourceId = `hproj-${"a".repeat(64)}`;
const bridgeId = `hproj-${"b".repeat(64)}`;
const revisionA = `tnr-${"c".repeat(32)}`;
const revisionB = `tnr-${"d".repeat(32)}`;
const compositionId = `tnc-${"e".repeat(32)}`;
const draftId = `drf_${"1".repeat(32)}`;
const reviewId = `rvw_${"2".repeat(32)}`;

const context = {
  source_projections: [{
    projection_id: sourceId,
    source_asset_id: "asset",
    source_document_id: "document",
    label: "Aircraft systems",
    preview_url: `/research/twin-notes/merge-context/source-projections/${sourceId}/preview`,
  }],
  twin_sources: [{
    kind: "composition" as const,
    id: compositionId,
    label: "Composition (2 revisions)",
    html_url: `/research/twin-notes/merge-context/composition/${compositionId}/preview`,
    revisions: [
      { member_ordinal: 0, revision_id: revisionA, notes: [{ note_ordinal: 0, text: "Alpha insight", source_count: 2 }] },
      { member_ordinal: 1, revision_id: revisionB, notes: [{ note_ordinal: 0, text: "Beta insight", source_count: 1 }] },
    ],
  }],
  limits: { source_projections: 200, twin_sources: 400, notes: 1000 },
};

describe("Cycle 55 twin-note canonical merge workstation", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.context.mockResolvedValue(context);
    mocks.bridge.mockResolvedValue({
      projection_id: bridgeId,
      source_projection_id: sourceId,
      twin_source: { kind: "composition", id: compositionId },
      member_count: 2,
      hosted_html_sha256: "f".repeat(64),
      merge_draft_input: { projection_ids: [sourceId, bridgeId] },
    });
    mocks.draft.mockResolvedValue({
      draft_id: draftId, canonical_sha256: "3".repeat(64), manifest_sha256: "4".repeat(64),
      sanitizer_policy: "canonical", sanitizer_version: "1", projection_ids: [sourceId, bridgeId],
    });
    mocks.review.mockResolvedValue({
      review_id: reviewId, draft_id: draftId, canonical_sha256: "3".repeat(64),
      manifest_sha256: "4".repeat(64), acknowledgement_version: "v1",
    });
    mocks.apply.mockImplementation((_review: string, operation: string) => Promise.resolve({
      operation_id: operation, derived_asset_id: "asset-derived", revision_id: "rev-derived",
      content_sha256: "5".repeat(64), generation: 1, replayed: false,
    }));
  });

  it("preserves explicit note order through separate bridge, draft, review, and apply stages", async () => {
    const pending = vi.fn();
    render(<TwinNoteMergeWorkspace disabled={false} onPendingChange={pending} />);
    fireEvent.click(screen.getByText("Merge into derived asset"));
    await screen.findByRole("option", { name: "Aircraft systems" });
    fireEvent.change(screen.getByLabelText("Merge source projection"), { target: { value: sourceId } });
    fireEvent.change(screen.getByLabelText("Merge twin source"), { target: { value: `composition:${compositionId}` } });

    for (const title of ["Source HTML comparison", "Twin-note HTML comparison"]) {
      expect(screen.getByTitle(title).getAttribute("sandbox")).toBe("");
    }
    fireEvent.click(screen.getByText("Beta insight"));
    fireEvent.click(screen.getByText("Alpha insight"));
    fireEvent.click(screen.getByLabelText("Move merge note 2 up"));
    fireEvent.click(screen.getByText("Create merge projection"));
    await screen.findByLabelText("Canonical merge draft stage");
    expect(mocks.bridge.mock.calls[0][0].selected_notes).toEqual([
      { revision_id: revisionA, note_ordinal: 0 },
      { revision_id: revisionB, note_ordinal: 0 },
    ]);

    fireEvent.change(screen.getByLabelText("Derived asset title"), { target: { value: "Flight analysis" } });
    fireEvent.click(screen.getByText("Create canonical draft"));
    await screen.findByLabelText("Draft preview stage");
    expect(mocks.draft.mock.calls[0][0].projection_ids).toEqual([sourceId, bridgeId]);
    expect(mocks.review).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Create immutable review"));
    await screen.findByLabelText("Reviewed merge stage");
    expect(mocks.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Apply reviewed merge"));
    expect(await screen.findByText(/Applied as derived asset asset-derived/)).toBeTruthy();
    fireEvent.click(screen.getByText("Recreate draft"));
    await waitFor(() => expect(screen.queryByLabelText("Reviewed merge stage")).toBeNull());
    expect(screen.queryByText(/Applied as derived asset/)).toBeNull();
    expect(mocks.apply).toHaveBeenCalledTimes(1);
    expect(pending).toHaveBeenCalledWith(true);
    expect(pending).toHaveBeenLastCalledWith(false);
  });

  it("invalidates downstream authority and refuses a late bridge response", async () => {
    let settle: ((value: unknown) => void) | undefined;
    mocks.bridge.mockReturnValue(new Promise((resolve) => { settle = resolve; }));
    render(<TwinNoteMergeWorkspace disabled={false} onPendingChange={vi.fn()} />);
    fireEvent.click(screen.getByText("Merge into derived asset"));
    await screen.findByRole("option", { name: "Aircraft systems" });
    const source = screen.getByLabelText("Merge source projection");
    fireEvent.change(source, { target: { value: sourceId } });
    fireEvent.change(screen.getByLabelText("Merge twin source"), { target: { value: `composition:${compositionId}` } });
    fireEvent.click(screen.getByText("Alpha insight"));
    fireEvent.click(screen.getByText("Create merge projection"));
    await waitFor(() => expect(mocks.bridge).toHaveBeenCalledTimes(1));
    fireEvent.change(source, { target: { value: "" } });
    settle?.({
      projection_id: bridgeId, source_projection_id: sourceId,
      twin_source: { kind: "composition", id: compositionId }, member_count: 1,
      hosted_html_sha256: "f".repeat(64), merge_draft_input: { projection_ids: [sourceId, bridgeId] },
    });
    await waitFor(() => expect(screen.queryByLabelText("Canonical merge draft stage")).toBeNull());
    expect(screen.queryByText("Merge command in progress…")).toBeNull();
  });

  it("rejects cross-origin and non-contract preview URLs", () => {
    expect(() => mergePreviewUrl("https://evil.example/preview")).toThrow();
    expect(() => mergePreviewUrl("/research/twin-notes/revisions/tnr-" + "a".repeat(32))).toThrow();
    expect(() => mergePreviewUrl(`/research/derived-assets/merge/previews/${draftId}`)).toThrow();
  });
});
