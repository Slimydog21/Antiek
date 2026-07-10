import { describe, expect, it, vi, beforeEach } from "vitest";

import { launchFloatingDeepResearch } from "./launchFloatingDeepResearch";

const openEngagementSession = vi.fn();
const openDeepResearchFromHighlight = vi.fn((_body: unknown) => "wdr_fsess_1");

vi.mock("../../api/engagement", () => ({
  openEngagementSession: (body: unknown) => openEngagementSession(body),
}));

vi.mock("../../workspace/deepResearchWindow", () => ({
  openDeepResearchFromHighlight: (body: unknown) =>
    openDeepResearchFromHighlight(body),
}));

describe("launchFloatingDeepResearch", () => {
  beforeEach(() => {
    openEngagementSession.mockReset();
    openDeepResearchFromHighlight.mockClear();
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
    });

    expect(openEngagementSession).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "doc-1",
        selection_text: "Attention is content-addressable",
        view_mode: "floating",
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
