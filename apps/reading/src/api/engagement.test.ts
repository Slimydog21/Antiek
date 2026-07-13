import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  attachSourceRefs,
  confirmCollectiveSubstackExcerpt,
  confirmSessionTwins,
  fetchResearchContext,
  getOwnedCollectiveUnit,
  getCollectiveExecutionStatus,
  listEngagementSessions,
  listOwnedEngagementSessions,
  listOwnedCollectiveUnits,
  mergeEngagementSessions,
  mergeSpawnOutputs,
  openEngagementSession,
  prepareCollectiveExecution,
  previewCollectiveExecutionReadiness,
  reviewCollectiveSubstackExcerpt,
  spawnFromHighlight,
  updateEngagementSessionView,
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

  it("lists durable sessions and persists view CAS", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          parent_asset_id: "book-1",
          sessions: [],
          count: 0,
          view_format: "html",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: "fsess_0123456789abcdef",
          view_mode: "full",
          view_format: "html",
        }),
      });
    await listEngagementSessions("book-1");
    await updateEngagementSessionView({
      session_id: "fsess_0123456789abcdef",
      mode: "full",
      expected_mode: "floating",
    });
    expect(mockFetch.mock.calls[0][0]).toBe(
      "/engagement/sessions/asset/book-1?include_html=false",
    );
    expect(mockFetch.mock.calls[1][0]).toBe(
      "/engagement/sessions/fsess_0123456789abcdef/view",
    );
    const init = mockFetch.mock.calls[1][1] as { body: string };
    expect(JSON.parse(init.body)).toEqual({
      mode: "full",
      expected_mode: "floating",
    });
  });

  it("sends confirmed merge receipt authority", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        mode: "into_parent",
        merge_receipt_id: "mrcpt_123",
        merge_receipt_state: "applied",
      }),
    });
    await mergeEngagementSessions({
      parent_asset_id: "book-1",
      session_ids: ["fsess_0123456789abcdef"],
      mode: "into_parent",
      confirm_parent_write: true,
      expected_parent_sha256: "a".repeat(64),
      idempotency_key: "browser-confirm-001",
    });
    const init = mockFetch.mock.calls[0][1] as { body: string };
    const body = JSON.parse(init.body);
    expect(body.idempotency_key).toBe("browser-confirm-001");
    expect(body.expected_parent_sha256).toBe("a".repeat(64));
    expect(body.confirm_parent_write).toBe(true);
  });

  it("requests bounded owner-wide discovery without sending owner identity", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ sessions: [], count: 0, next_cursor: null }),
    });
    await listOwnedEngagementSessions({
      cursor: "fsess_0123456789abcdef",
      limit: 25,
    });
    const url = String(mockFetch.mock.calls[0][0]);
    expect(url).toContain("/engagement/sessions/owned?");
    expect(url).toContain("cursor=fsess_0123456789abcdef");
    expect(url).toContain("limit=25");
    expect(url).not.toContain("owner_id=");
  });

  it("pages and resolves owner collectives without caller-supplied owner identity", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ collectives: [], count: 0, next_cursor: null }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ collective_unit_id: "cunit_aaaaaaaaaaaaaaaaaaaaaaaa" }),
      });
    await listOwnedCollectiveUnits({
      cursor: "cunit_aaaaaaaaaaaaaaaaaaaaaaaa",
      limit: 15,
    });
    await getOwnedCollectiveUnit("cunit_aaaaaaaaaaaaaaaaaaaaaaaa");
    const listUrl = String(mockFetch.mock.calls[0][0]);
    expect(listUrl).toContain("/engagement/sessions/collective/owned?");
    expect(listUrl).toContain("cursor=cunit_aaaaaaaaaaaaaaaaaaaaaaaa");
    expect(listUrl).toContain("limit=15");
    expect(listUrl).not.toContain("owner_id=");
    expect(mockFetch.mock.calls[1][0]).toBe(
      "/engagement/sessions/collective/cunit_aaaaaaaaaaaaaaaaaaaaaaaa",
    );
    expect(mockFetch.mock.calls[1][1]).toEqual({ cache: "no-store" });
  });

  it("reviews and confirms one private Substack excerpt without owner or signing material", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ review_id: "sureview_1" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ overlay_id: "csubrev_1" }) });
    await reviewCollectiveSubstackExcerpt("cunit_aaaaaaaaaaaaaaaaaaaaaaaa", {
      expected_collective_preview_sha256: "b".repeat(64),
      ref_id: "sref_aaaaaaaaaaaaaaaa",
      selection_text: "selected",
      source_representation_sha256: "c".repeat(64),
      source_representation_bytes: 100,
      source_byte_start: 10,
      authorization_lifetime_minutes: 30,
      owner_affirms_lawful_access: true,
      owner_affirms_provider_processing: true,
      partial_excerpt_affirmed: true,
      redistribution_authorized: false,
      training_authorized: false,
      publication_authorized: false,
      idempotency_key: "review-key-001",
    });
    await confirmCollectiveSubstackExcerpt("cunit_aaaaaaaaaaaaaaaaaaaaaaaa", {
      review_id: "sureview_aaaaaaaaaaaaaaaaaaaaaaaa",
      expected_review_preview_sha256: "d".repeat(64),
      idempotency_key: "confirm-key-001",
    });
    const reviewBody = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body);
    expect(reviewBody).not.toHaveProperty("owner_id");
    expect(reviewBody).not.toHaveProperty("canonical_url");
    expect(reviewBody).not.toHaveProperty("signing_key");
    expect(String(mockFetch.mock.calls[0][0])).toContain("/substack-excerpts/review");
    expect(String(mockFetch.mock.calls[1][0])).toContain("/substack-excerpts/confirm");
  });

  it("prepares and polls a collective execution without caller owner authority", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ job_id: "moil_1" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ state: "queued" }) });
    await prepareCollectiveExecution("cunit_aaaaaaaaaaaaaaaaaaaaaaaa", {
      session_id: "fsess_0123456789abcdef",
      expected_preview_sha256: "b".repeat(64),
      idempotency_key: "execution-prepare-001",
      duration_minutes: 60,
      model_id: "test-model",
      research_tier: "wrestle",
      fanout_depth: 3,
    });
    await getCollectiveExecutionStatus(
      "cunit_aaaaaaaaaaaaaaaaaaaaaaaa",
      "cexec_cccccccccccccccccccccccc",
    );
    expect(mockFetch.mock.calls[0][0]).toBe(
      "/engagement/sessions/collective/cunit_aaaaaaaaaaaaaaaaaaaaaaaa/execution/prepare",
    );
    const init = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(init.body)).not.toHaveProperty("owner_id");
    expect(mockFetch.mock.calls[1][0]).toBe(
      "/engagement/sessions/collective/cunit_aaaaaaaaaaaaaaaaaaaaaaaa/execution/cexec_cccccccccccccccccccccccc",
    );
  });

  it("requests a no-store non-conferring publication readiness preview", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ consent_enabled: false }) });
    await previewCollectiveExecutionReadiness("cunit_aaaaaaaaaaaaaaaaaaaaaaaa", {
      schema_version: 1,
      expected_collective_preview_sha256: "b".repeat(64),
      duration_minutes: 60,
      substack_overlays: [
        {
          ref_id: "sref_1111111111111111",
          overlay_id: "csubrev_222222222222222222222222",
          overlay_sha256: "c".repeat(64),
        },
      ],
    });
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/execution/readiness-preview");
    expect(init.cache).toBe("no-store");
    expect(JSON.parse(String(init.body))).not.toHaveProperty("owner_id");
    expect(JSON.parse(String(init.body))).not.toHaveProperty("idempotency_key");
  });

  it("sends pinned preview authority for confirmed twin promotion", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        twin_context_mode: "confirmed_mutating",
        graph_write: true,
        promotion_receipt_id: "tpr_123",
        promotion_receipt_state: "applied",
      }),
    });
    await confirmSessionTwins({
      session_id: "fsess_0123456789abcdef",
      expected_preview_sha256: "a".repeat(64),
      idempotency_key: "browser-twin-confirm-001",
      kinds: ["insight"],
      note_ids: ["twin_1"],
    });
    expect(mockFetch.mock.calls[0][0]).toBe(
      "/engagement/sessions/fsess_0123456789abcdef/twins/promote-confirm",
    );
    const init = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(init.body)).toEqual(
      expect.objectContaining({
        expected_preview_sha256: "a".repeat(64),
        idempotency_key: "browser-twin-confirm-001",
        kinds: ["insight"],
        note_ids: ["twin_1"],
      }),
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
