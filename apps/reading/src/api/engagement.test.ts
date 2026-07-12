import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  attachSourceRefs,
  commitReviewedMergeDraft,
  fetchResearchContext,
  fetchTwinNotes,
  getCanonicalMergeHtml,
  mergeSpawnOutputs,
  openEngagementSession,
  spawnFromHighlight,
} from "./engagement";

const mockFetch = vi.fn();

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: (...args: unknown[]) => mockFetch(...args),
}));

describe("engagement API client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("spawnFromHighlight posts highlight + refs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        spawn_id: "spn_1",
        investigation_id: "inv_1",
        parent_asset_id: "paper",
        goal: "g",
        status: "reserved",
        source_references: [{ ref_id: "sref_1", kind: "arxiv", raw: "1706.03762" }],
        view_format: "html",
      }),
    });
    const out = await spawnFromHighlight({
      asset_id: "paper",
      selection_text: "hi",
      references: ["1706.03762"],
    });
    expect(out.spawn_id).toBe("spn_1");
    expect(out.view_format).toBe("html");
    expect(mockFetch).toHaveBeenCalledWith(
      "/engagement/spawn-from-highlight",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("attachSourceRefs posts refs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        spawn_id: "spn_1",
        source_references: [],
        view_format: "html",
      }),
    });
    await attachSourceRefs("spn_1", ["https://x.substack.com/p/y"]);
    expect(mockFetch).toHaveBeenCalledWith(
      "/engagement/attach-refs",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("fetchResearchContext returns prompt_block shape", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        asset_id: "a",
        twin_units: [],
        source_references: [],
        view_format: "html",
        twin_count: 0,
        ref_count: 0,
        prompt_block: "# Research context\n",
      }),
    });
    const ctx = await fetchResearchContext({ asset_id: "a" });
    expect(ctx.prompt_block).toContain("Research context");
  });

  it("openEngagementSession posts to sessions/open", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: "fsess_1",
        spawn_id: "spn_1",
        investigation_id: "inv_1",
        parent_asset_id: "a",
        selection_text: "x",
        status: "reserved",
        view_mode: "floating",
        view_format: "html",
      }),
    });
    const s = await openEngagementSession({
      asset_id: "a",
      selection_text: "x",
      view_mode: "floating",
    });
    expect(s.session_id).toBe("fsess_1");
    expect(mockFetch.mock.calls[0][0]).toBe("/engagement/sessions/open");
  });

  it("mergeSpawnOutputs posts draft_combined by default", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        mode: "draft_combined",
        parent_asset_id: "book-1",
        document_id: "draft_book-1_abc",
        source_spawn_ids: ["spn_1"],
        sections_merged: 2,
        draft_leaves_parent: true,
        parent_document_id: "book-1",
        view_format: "html",
        product_panel: "engagement_merge",
        source: "engagement_spine.merge_spawn_outputs",
        notes: ["Draft-combined document; parent asset unchanged"],
        html: "<p>Merge mode: draft_combined</p>",
      }),
    });
    const out = await mergeSpawnOutputs({
      parent_asset_id: "book-1",
      spawn_ids: ["spn_1"],
    });
    expect(out.mode).toBe("draft_combined");
    expect(out.draft_leaves_parent).toBe(true);
    expect(out.view_format).toBe("html");
    expect(mockFetch).toHaveBeenCalledWith(
      "/engagement/merge",
      expect.objectContaining({ method: "POST" }),
    );
    const init = mockFetch.mock.calls[0][1] as { body: string };
    const body = JSON.parse(init.body);
    expect(body.mode).toBe("draft_combined");
    expect(body.include_html).toBe(true);
  });

  it("commitReviewedMergeDraft sends the exact review token and revision", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        deliverable_id: "dlv-reviewed",
        draft_document_id: "draft-reviewed",
        old_revision: null,
        new_revision: "b".repeat(64),
        section_id: "sec-reviewed",
        node_ids: ["node-reviewed"],
        paragraph_count: 1,
        draft_sha256: "a".repeat(64),
        view_format: "html",
        html: "<article>Canonical</article>",
      }),
    });
    const committed = await commitReviewedMergeDraft({
      draft_document_id: "draft-reviewed",
      reviewed_draft_sha256: "a".repeat(64),
      target_deliverable_id: "dlv-reviewed",
      expected_revision: "new",
      create_combined: true,
    });
    expect(committed.deliverable_id).toBe("dlv-reviewed");
    expect(mockFetch).toHaveBeenCalledWith(
      "/engagement/merge/commit",
      expect.objectContaining({ method: "POST" }),
    );
    const init = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(init.body)).toEqual({
      draft_document_id: "draft-reviewed",
      reviewed_draft_sha256: "a".repeat(64),
      target_deliverable_id: "dlv-reviewed",
      expected_revision: "new",
      create_combined: true,
    });
  });

  it("getCanonicalMergeHtml reloads the canonical deliverable identity", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        deliverable_id: "dlv-canonical",
        section_id: "sec-canonical",
        revision: "b".repeat(64),
        draft_sha256: "a".repeat(64),
        view_format: "html",
        html: "<article>Reloaded canonical research</article>",
      }),
    });
    const result = await getCanonicalMergeHtml("dlv/canonical");
    expect(result.revision).toBe("b".repeat(64));
    expect(mockFetch).toHaveBeenCalledWith(
      "/engagement/merge/canonical/html?deliverable_id=dlv%2Fcanonical",
    );
  });

  it("fetchTwinNotes transports opaque asset identities losslessly", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        asset_id: "project/a %?#/مرحبا",
        note_count: 0,
        insight_count: 0,
        question_count: 0,
        notes: [],
        view_format: "html",
        product_panel: "twin_notes",
        source: "engagement_spine.twin",
      }),
    });
    const identity = "project/a %?#/مرحبا";
    const result = await fetchTwinNotes(identity, { includeHtml: true });
    expect(result.asset_id).toBe(identity);
    expect(mockFetch).toHaveBeenCalledWith(
      `/engagement/twins?${new URLSearchParams({ asset_id: identity, include_html: "true" })}`,
    );
  });

  it("throws on non-ok", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
    });
    await expect(
      spawnFromHighlight({ asset_id: "a", selection_text: "  " }),
    ).rejects.toThrow(/engagement API 400/);
  });
});
