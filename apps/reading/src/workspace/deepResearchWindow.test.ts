/**
 * Product path: openDeepResearchFromHighlight → registry + windowsStore.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const listEngagementSessions = vi.hoisted(() => vi.fn());
const updateEngagementSessionView = vi.hoisted(() => vi.fn());

vi.mock("../api/engagement", () => ({
  listEngagementSessions,
  updateEngagementSessionView,
}));

import {
  DEEP_RESEARCH_WINDOW_KIND,
  openDeepResearchFromHighlight,
  reopenDeepResearchWindowsForAsset,
  syncDeepResearchWindowModeDurably,
  windowIdForSession,
} from "./deepResearchWindow";
import { isWindowEligible } from "../components/windows/openWindow";
import { useWindows } from "./windowsStore";

const FIXTURE = {
  asset_id: "launch-asset",
  selection_text: "Transformer attention is content-addressable memory.",
  session_id: "fsess_launch_1",
  spawn_id: "spn_launch_1",
  investigation_id: "inv_launch_1",
  region_id: "r-launch-1",
  model_id: "launch-model",
  status: "reserved",
};

beforeEach(() => {
  useWindows.getState().reset();
  listEngagementSessions.mockReset();
  updateEngagementSessionView.mockReset();
});

describe("openDeepResearchFromHighlight", () => {
  it("opens a hostable deep_research_session window with identity payload", () => {
    expect(isWindowEligible(DEEP_RESEARCH_WINDOW_KIND)).toBe(true);
    const id = openDeepResearchFromHighlight(FIXTURE);
    expect(id).toBe(windowIdForSession(FIXTURE.session_id));
    const win = useWindows.getState().windows[id];
    expect(win).toBeTruthy();
    expect(win.kind).toBe(DEEP_RESEARCH_WINDOW_KIND);
    expect(win.payload.session_id).toBe(FIXTURE.session_id);
    expect(win.payload.spawn_id).toBe(FIXTURE.spawn_id);
    expect(win.payload.parent_asset_id).toBe("launch-asset");
    expect(String(win.payload.selection_text)).toContain("content-addressable");
    expect(win.payload.view_format).toBe("html");
  });

  it("re-invoke focuses the same window (stable id)", () => {
    const a = openDeepResearchFromHighlight(FIXTURE);
    const b = openDeepResearchFromHighlight(FIXTURE);
    expect(a).toBe(b);
    expect(Object.keys(useWindows.getState().windows)).toHaveLength(1);
  });

  it("rejects empty selection", () => {
    expect(() =>
      openDeepResearchFromHighlight({ ...FIXTURE, selection_text: "  " }),
    ).toThrow(/selection_text/);
  });

  it("carries research_tier into window payload (jk)", () => {
    const id = openDeepResearchFromHighlight({
      ...FIXTURE,
      research_tier: "wrestle",
    });
    const win = useWindows.getState().windows[id];
    expect(win.payload.research_tier).toBe("wrestle");
  });

  it("stamps seamless_highlight_dr on highlight → DR payload (afx)", () => {
    const id = openDeepResearchFromHighlight(FIXTURE);
    const win = useWindows.getState().windows[id];
    expect(win.payload.seamless_highlight_dr).toBe(true);
    expect(win.payload.view_format).toBe("html");
  });

  it("reopens owner-scoped durable sessions after reload", async () => {
    listEngagementSessions.mockResolvedValue({
      parent_asset_id: "launch-asset",
      count: 1,
      view_format: "html",
      sessions: [
        {
          ...FIXTURE,
          parent_asset_id: FIXTURE.asset_id,
          view_mode: "full",
          view_format: "html",
        },
      ],
    });
    const ids = await reopenDeepResearchWindowsForAsset("launch-asset");
    expect(ids).toEqual([windowIdForSession(FIXTURE.session_id)]);
    expect(useWindows.getState().windows[ids[0]]?.mode).toBe("full");
  });

  it("updates server view CAS before mirroring local chrome", async () => {
    const id = openDeepResearchFromHighlight(FIXTURE);
    let release!: () => void;
    updateEngagementSessionView.mockReturnValue(
      new Promise((resolve) => {
        release = () =>
          resolve({
            ...FIXTURE,
            parent_asset_id: FIXTURE.asset_id,
            view_mode: "full",
            view_format: "html",
          });
      }),
    );
    const pending = syncDeepResearchWindowModeDurably(
      FIXTURE.session_id,
      "full",
      "floating",
    );
    expect(useWindows.getState().windows[id]?.mode).toBe("floating");
    release();
    await pending;
    expect(useWindows.getState().windows[id]?.mode).toBe("full");
  });
});
