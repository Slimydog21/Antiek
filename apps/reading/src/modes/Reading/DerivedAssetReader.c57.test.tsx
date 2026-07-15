import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
vi.mock("./ReadingCompanion", () => ({ default: (props: { documentId: string }) => <aside data-testid="companion" data-document-id={props.documentId} /> }));
vi.mock("../shared/FloatMenu/FloatMenu", () => ({ default: () => null }));

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
    expect(mocks.getReading).toHaveBeenCalledWith(assetId, undefined);
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
