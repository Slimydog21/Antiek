import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import DerivedAssetReader from "./DerivedAssetReader";

const mocks = vi.hoisted(() => ({ getReading: vi.fn(), getCollection: vi.fn(), open: vi.fn() }));
vi.mock("../../api/research", () => ({
  getDerivedAssetReading: (...args: unknown[]) => mocks.getReading(...args),
  getDerivedEvidenceCollection: (...args: unknown[]) => mocks.getCollection(...args),
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
    <Route path="/read/derived/evidence/:collectionId" element={<DerivedAssetReader />} />
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

  it("opens a collection permalink on its exact historical HTML and navigates ordered evidence", async () => {
    const collectionId = `dec_${"d".repeat(32)}`;
    const source = { derived_asset_id: assetId, revision_id: revisionId,
      content_sha256: hash, generation: 4, citation_id: `dchunk_${"e".repeat(64)}`,
      chunk_ordinal: 0, chunk_text_sha256: "f".repeat(64), excerpt: "Bypass ratio matters." };
    mocks.getCollection.mockResolvedValue({
      collection_id: collectionId, label: "Engine evidence", derived_asset_id: assetId,
      revision_id: revisionId, content_sha256: hash, generation: 4, version: 1,
      member_count: 2, collection_sha256: "1".repeat(64), created_at: "now",
      updated_at: "now", etag: '"etag"', is_current: false,
      sources: [source, { ...source, citation_id: `dchunk_${"2".repeat(64)}`,
        chunk_ordinal: 1, chunk_text_sha256: "3".repeat(64), excerpt: "Fuel burn falls." }],
      locations: [
        { citation_id: source.citation_id, chunk_ordinal: 0,
          member_index: 0, section_anchor: "turbofan", section_path: "Engines / Turbofan" },
        { citation_id: `dchunk_${"2".repeat(64)}`, chunk_ordinal: 1,
          member_index: 0, section_anchor: "turbofan", section_path: "Engines / Efficiency" },
      ],
    });
    mocks.getReading.mockResolvedValue({ ...model, is_current: false });
    mount(`/read/derived/evidence/${collectionId}`);
    expect(await screen.findByRole("heading", { name: "Engine evidence" })).toBeTruthy();
    expect(mocks.getCollection).toHaveBeenCalledWith(collectionId);
    expect(mocks.getReading).toHaveBeenCalledWith(assetId, revisionId);
    const target = screen.getByRole("heading", { name: "Turbofan" });
    target.scrollIntoView = vi.fn();
    target.animate = vi.fn() as unknown as typeof target.animate;
    fireEvent.click(screen.getByRole("button", { name: /1\. Engines \/ Turbofan/ }));
    expect(target.scrollIntoView).toHaveBeenCalled();
    expect(target.animate).toHaveBeenCalled();
    expect(mocks.open).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Research collection" }));
    expect(mocks.open).toHaveBeenCalledWith("ChaseThread", expect.objectContaining({
      evidenceCollection: { collectionId, etag: '"etag"' },
      parentInvestigationId: `read-${assetId}:${revisionId}`,
    }), { mode: "floating", title: "Engine evidence" });
  });

  it("renders no HTML when collection and exact reading identities disagree", async () => {
    const collectionId = `dec_${"4".repeat(32)}`;
    const source = { derived_asset_id: assetId, revision_id: revisionId,
      content_sha256: hash, generation: 4, citation_id: `dchunk_${"4".repeat(64)}`,
      chunk_ordinal: 0, chunk_text_sha256: "5".repeat(64), excerpt: "Mismatch." };
    mocks.getCollection.mockResolvedValue({ collection_id: collectionId,
      derived_asset_id: assetId, revision_id: revisionId, content_sha256: hash,
      generation: 4, member_count: 2, sources: [source, { ...source,
        citation_id: `dchunk_${"6".repeat(64)}`, chunk_ordinal: 1 }],
      locations: [
        { citation_id: `dchunk_${"0".repeat(64)}`, chunk_ordinal: 0,
          member_index: 0, section_anchor: "turbofan", section_path: "Mismatch" },
        { citation_id: `dchunk_${"6".repeat(64)}`, chunk_ordinal: 1,
          member_index: 0, section_anchor: "turbofan", section_path: "Second" },
      ] });
    mocks.getReading.mockResolvedValue(model);
    mount(`/read/derived/evidence/${collectionId}`);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain(
      "could not be verified",
    ));
    expect(screen.queryByRole("article")).toBeNull();
  });

  it("never commits an older collection after navigation to a newer permalink", async () => {
    const oldId = `dec_${"5".repeat(32)}`;
    const nextId = `dec_${"6".repeat(32)}`;
    let resolveOld: (value: unknown) => void = () => undefined;
    const oldRequest = new Promise((resolve) => { resolveOld = resolve; });
    const source = { derived_asset_id: assetId, revision_id: revisionId,
      content_sha256: hash, generation: 4, citation_id: `dchunk_${"7".repeat(64)}`,
      chunk_ordinal: 0, chunk_text_sha256: "8".repeat(64), excerpt: "Newest passage." };
    const nextCollection = { collection_id: nextId, label: "New collection",
      derived_asset_id: assetId, revision_id: revisionId, content_sha256: hash,
      generation: 4, member_count: 2, sources: [source, { ...source,
        citation_id: `dchunk_${"9".repeat(64)}`, chunk_ordinal: 1 }],
      locations: [
        { citation_id: source.citation_id, chunk_ordinal: 0, member_index: 0,
          section_anchor: "turbofan", section_path: "New / One" },
        { citation_id: `dchunk_${"9".repeat(64)}`, chunk_ordinal: 1, member_index: 0,
          section_anchor: "turbofan", section_path: "New / Two" },
      ], etag: '"new"', is_current: false };
    mocks.getCollection.mockImplementation((id: string) =>
      id === oldId ? oldRequest : Promise.resolve(nextCollection));
    mocks.getReading.mockResolvedValue({ ...model, is_current: false });
    const router = createMemoryRouter([
      { path: "/read/derived/evidence/:collectionId", element: <DerivedAssetReader /> },
    ], { initialEntries: [`/read/derived/evidence/${oldId}`] });
    render(<RouterProvider router={router} />);
    await act(async () => { await router.navigate(`/read/derived/evidence/${nextId}`); });
    expect(await screen.findByRole("heading", { name: "New collection" })).toBeTruthy();
    await act(async () => { resolveOld({ ...nextCollection, collection_id: oldId,
      label: "Old collection" }); await oldRequest; });
    expect(screen.queryByRole("heading", { name: "Old collection" })).toBeNull();
    expect(screen.getByRole("heading", { name: "New collection" })).toBeTruthy();
  });

  it("never commits an older exact reading after a newer permalink has loaded", async () => {
    const oldId = `dec_${"a".repeat(32)}`;
    const nextId = `dec_${"b".repeat(32)}`;
    let resolveOldReading: (value: unknown) => void = () => undefined;
    const oldReading = new Promise((resolve) => { resolveOldReading = resolve; });
    const source = { derived_asset_id: assetId, revision_id: revisionId,
      content_sha256: hash, generation: 4, citation_id: `dchunk_${"a".repeat(64)}`,
      chunk_ordinal: 0, chunk_text_sha256: "b".repeat(64), excerpt: "Exact passage." };
    const collectionFor = (id: string, label: string) => ({ collection_id: id, label,
      derived_asset_id: assetId, revision_id: revisionId, content_sha256: hash,
      generation: 4, member_count: 2, sources: [source, { ...source,
        citation_id: `dchunk_${"c".repeat(64)}`, chunk_ordinal: 1 }], locations: [
        { citation_id: source.citation_id, chunk_ordinal: 0, member_index: 0,
          section_anchor: "turbofan", section_path: "Exact / One" },
        { citation_id: `dchunk_${"c".repeat(64)}`, chunk_ordinal: 1, member_index: 0,
          section_anchor: "turbofan", section_path: "Exact / Two" },
      ], etag: `"${id}"`, is_current: false });
    mocks.getCollection.mockImplementation((id: string) => Promise.resolve(
      collectionFor(id, id === oldId ? "Old reading" : "New reading"),
    ));
    mocks.getReading.mockImplementationOnce(() => oldReading)
      .mockResolvedValueOnce({ ...model, title: "Newest HTML", is_current: false });
    const router = createMemoryRouter([
      { path: "/read/derived/evidence/:collectionId", element: <DerivedAssetReader /> },
    ], { initialEntries: [`/read/derived/evidence/${oldId}`] });
    render(<RouterProvider router={router} />);
    await waitFor(() => expect(mocks.getReading).toHaveBeenCalledTimes(1));
    await act(async () => { await router.navigate(`/read/derived/evidence/${nextId}`); });
    expect(await screen.findByRole("heading", { name: "Newest HTML" })).toBeTruthy();
    await act(async () => { resolveOldReading({ ...model, title: "Stale HTML" });
      await oldReading; });
    expect(screen.queryByRole("heading", { name: "Stale HTML" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Newest HTML" })).toBeTruthy();
  });
});
