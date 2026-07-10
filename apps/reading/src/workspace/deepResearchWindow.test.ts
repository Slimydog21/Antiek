/**
 * Product path: openDeepResearchFromHighlight → registry + windowsStore.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  DEEP_RESEARCH_WINDOW_KIND,
  openDeepResearchFromHighlight,
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
});
