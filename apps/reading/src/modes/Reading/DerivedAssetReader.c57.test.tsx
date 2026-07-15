import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import DerivedAssetReader from "./DerivedAssetReader";

const mocks = vi.hoisted(() => ({ getReading: vi.fn(), open: vi.fn() }));
vi.mock("../../api/research", () => ({
  getDerivedAssetReading: (...args: unknown[]) => mocks.getReading(...args),
}));
vi.mock("../../workspace/WorkspaceStore", () => ({
  useWorkspace: (selector: (state: { open: typeof mocks.open }) => unknown) => selector({ open: mocks.open }),
}));
vi.mock("./DerivedRevisionCompanion", () => ({ default: (props: { model: { derived_asset_id: string; revision_id: string }; onFollowCitation: (citation: unknown) => void }) => <aside data-testid="companion" data-document-id={props.model.derived_asset_id} data-revision-id={props.model.revision_id}><button onClick={() => props.onFollowCitation({ citation_id: `dchunk_${"d".repeat(64)}`, chunk_ordinal: 3, member_index: 0, section_anchor: "turbofan", section_path: "Engines / Turbofan", text: "Bypass ratio matters.", text_sha256: "e".repeat(64) })}>Follow citation</button></aside> }));
vi.mock("../shared/FloatMenu/FloatMenu", () => ({ default: (props: { investigationId: string }) => <div data-testid="float-menu" data-thread-id={props.investigationId} /> }));

const assetId = `ast_${"a".repeat(32)}`;
const revisionId = `rev_${"b".repeat(32)}`;
const hash = "c".repeat(64);
const model = {
  derived_asset_id: assetId,
  title: "Aircraft engines",
  asset_kind: "analysis" as const,
  revision_id: revisionId,
  content_sha256: hash,
  generation: 4,
  member_count: 3,
  is_current: true,
  canonical_html: '<section><h2 id="turbofan">Turbofan</h2><p>Bypass ratio matters.</p></section>',
  stable_reader_path: `/read/derived/${assetId}`,
  exact_reader_path: `/read/derived/${assetId}/revisions/${revisionId}`,
};

function mount(path = `/read/derived/${assetId}`) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/read/derived/:assetId" element={<DerivedAssetReader />} />
    <Route path="/read/derived/:assetId/revisions/:revisionId" element={<DerivedAssetReader />} />
  </Routes></MemoryRouter>);
}

describe("Cycle 57 derived HTML reader", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("renders verified canonical HTML as selectable DOM with exact identity", async () => {
    mocks.getReading.mockResolvedValue(model);
    mount();
    expect(await screen.findByRole("heading", { name: "Aircraft engines" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Turbofan" })).toBeTruthy();
    const article = screen.getByRole("article");
    expect(article.dataset.derivedAssetId).toBe(assetId);
    expect(article.dataset.revisionId).toBe(revisionId);
    expect(article.dataset.contentSha256).toBe(hash);
    expect(article.innerHTML).toBe(model.canonical_html);
    expect(screen.getByTestId("companion").dataset.documentId).toBe(assetId);
    expect(screen.getByTestId("companion").dataset.revisionId).toBe(revisionId);
    const threadId = `read-${assetId}:${revisionId}`;
    expect(screen.getByTestId("float-menu").dataset.threadId).toBe(threadId);
    expect(mocks.getReading).toHaveBeenCalledWith(assetId, undefined);
    expect(mocks.open).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Follow citation"));
    expect(mocks.open).toHaveBeenCalledWith("ChaseThread", expect.objectContaining({
      spawnContext: "Bypass ratio matters.",
      parentInvestigationId: `read-${assetId}:${revisionId}`,
      sourceProvenance: expect.objectContaining({
        derivedCitationId: `dchunk_${"d".repeat(64)}`,
        derivedChunkOrdinal: 3,
        derivedChunkTextSha256: "e".repeat(64),
      }),
    }), { mode: "floating", title: "Follow this" });
  });

  it("pins immutable routes and refuses conflicting server identity", async () => {
    mocks.getReading.mockResolvedValueOnce(model).mockResolvedValueOnce({ ...model, revision_id: `rev_${"d".repeat(32)}` });
    const view = mount(`/read/derived/${assetId}/revisions/${revisionId}`);
    await screen.findByRole("heading", { name: "Turbofan" });
    expect(mocks.getReading).toHaveBeenCalledWith(assetId, revisionId);
    view.unmount();
    mount(`/read/derived/${assetId}/revisions/${revisionId}`);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("could not be verified"));
    expect(screen.queryByRole("heading", { name: "Turbofan" })).toBeNull();
  });
});
