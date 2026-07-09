import { describe, expect, it, vi, beforeEach } from "vitest";

import { launchFloatingDeepResearch } from "./launchFloatingDeepResearch";

const openEngagementSession = vi.fn();
const openDeepResearchFromHighlight = vi.fn(() => "wdr_fsess_1");
const fetchDecisionTreeSelection = vi.fn();

vi.mock("../../api/engagement", () => ({
  openEngagementSession: (...args: unknown[]) => openEngagementSession(...args),
}));

vi.mock("../../api/settings", () => ({
  fetchDecisionTreeSelection: (...args: unknown[]) =>
    fetchDecisionTreeSelection(...args),
}));

vi.mock("../../workspace/deepResearchWindow", () => ({
  openDeepResearchFromHighlight: (...args: unknown[]) =>
    openDeepResearchFromHighlight(...args),
}));

describe("launchFloatingDeepResearch residual cc/cy", () => {
  beforeEach(() => {
    openEngagementSession.mockReset();
    openDeepResearchFromHighlight.mockClear();
    fetchDecisionTreeSelection.mockReset();
    fetchDecisionTreeSelection.mockResolvedValue({
      installed: false,
      model_id: null,
      provider_id: null,
    });
  });

  it("opens engagement session then floating deep research window", async () => {
    openEngagementSession.mockResolvedValue({
      session_id: "fsess_1",
      spawn_id: "spn_1",
      investigation_id: "inv_1",
      parent_asset_id: "doc-1",
      selection_text: "Attention is content-addressable",
      status: "reserved",
      view_mode: "floating",
      view_format: "html",
      goal: "Deep-research the passage",
      model_id: null,
    });

    const out = await launchFloatingDeepResearch({
      asset_id: "doc-1",
      selection_text: "Attention is content-addressable",
      page: 0,
      references: ["arxiv:1706.03762", "  "],
    });

    expect(openEngagementSession).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "doc-1",
        selection_text: "Attention is content-addressable",
        view_mode: "floating",
        references: ["arxiv:1706.03762"],
        model_id: null,
      }),
    );
    expect(openDeepResearchFromHighlight).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: "fsess_1",
        spawn_id: "spn_1",
        investigation_id: "inv_1",
        asset_id: "doc-1",
        mode: "floating",
      }),
    );
    expect(out.window_id).toBe("wdr_fsess_1");
    expect(out.view_format).toBe("html");
    expect(out.session_id).toBe("fsess_1");
    expect(out.model_id).toBeNull();
  });

  it("resolves decision-tree model_id when caller omits model (cy)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      installed: true,
      model_id: "claude-opus-4-8",
      provider_id: "anthropic",
    });
    openEngagementSession.mockResolvedValue({
      session_id: "fsess_cy",
      spawn_id: "spn_cy",
      investigation_id: "inv_cy",
      parent_asset_id: "doc-1",
      selection_text: "twin notes",
      status: "reserved",
      view_mode: "floating",
      view_format: "html",
      goal: "g",
      model_id: "claude-opus-4-8",
    });

    const out = await launchFloatingDeepResearch({
      asset_id: "doc-1",
      selection_text: "twin notes",
    });

    expect(fetchDecisionTreeSelection).toHaveBeenCalled();
    expect(openEngagementSession).toHaveBeenCalledWith(
      expect.objectContaining({ model_id: "claude-opus-4-8" }),
    );
    expect(openDeepResearchFromHighlight).toHaveBeenCalledWith(
      expect.objectContaining({ model_id: "claude-opus-4-8" }),
    );
    expect(out.model_id).toBe("claude-opus-4-8");
  });

  it("explicit model_id wins over decision-tree (cy)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      installed: true,
      model_id: "tree-model",
      provider_id: "x",
    });
    openEngagementSession.mockResolvedValue({
      session_id: "fsess_x",
      spawn_id: "spn_x",
      investigation_id: "inv_x",
      parent_asset_id: "doc-1",
      selection_text: "hello",
      status: "reserved",
      view_mode: "floating",
      view_format: "html",
      goal: "g",
      model_id: "explicit-model",
    });

    await launchFloatingDeepResearch({
      asset_id: "doc-1",
      selection_text: "hello",
      model_id: "explicit-model",
    });

    expect(fetchDecisionTreeSelection).not.toHaveBeenCalled();
    expect(openEngagementSession).toHaveBeenCalledWith(
      expect.objectContaining({ model_id: "explicit-model" }),
    );
  });

  it("driver fetch failure is non-fatal (cy)", async () => {
    fetchDecisionTreeSelection.mockRejectedValue(new Error("offline"));
    openEngagementSession.mockResolvedValue({
      session_id: "fsess_f",
      spawn_id: "spn_f",
      investigation_id: "inv_f",
      parent_asset_id: "doc-1",
      selection_text: "hello",
      status: "reserved",
      view_mode: "floating",
      view_format: "html",
      goal: "g",
      model_id: null,
    });

    const out = await launchFloatingDeepResearch({
      asset_id: "doc-1",
      selection_text: "hello",
    });

    expect(openEngagementSession).toHaveBeenCalledWith(
      expect.objectContaining({ model_id: null }),
    );
    expect(out.model_id).toBeNull();
  });

  it("rejects empty selection", async () => {
    await expect(
      launchFloatingDeepResearch({
        asset_id: "doc-1",
        selection_text: "  ",
      }),
    ).rejects.toThrow(/selection_text/);
    expect(openEngagementSession).not.toHaveBeenCalled();
  });
});
