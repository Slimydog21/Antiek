import { describe, expect, it } from "vitest";
import {
  composeFloatingFullscreenOpen,
  formatFloatingFullscreenOpenSummary,
} from "./floatingFullscreenOpenCompose";
import type { FloatingDeepResearchInstance } from "./floatingDeepResearch";

describe("composeFloatingFullscreenOpen", () => {
  it("spawn from highlight and open fullscreen", () => {
    const c = composeFloatingFullscreenOpen({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      highlight: "Scaling laws claim from page 12",
      prompt: "What evidence supports this?",
      gated: false,
      operator_ack: true,
    });
    expect(c.instance.view_mode).toBe("fullscreen");
    expect(c.view_mode.action_applied).toBe(true);
    expect(c.tray.action).toBe("fullscreen_one");
    expect(c.tray.tray_ready).toBe(true);
    expect(c.fullscreen_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.pack_dispatched).toBe(false);
    expect(c.authority).toBe("floating_fullscreen_open_compose_advisory");
    expect(formatFloatingFullscreenOpenSummary(c)).toMatch(
      /live_dispatched=false/,
    );
  });

  it("existing instance path", () => {
    const existing: FloatingDeepResearchInstance = {
      instance_id: "fdr_existing",
      parent_asset_id: "asset-1",
      highlight: "prior float",
      prompt: "chase",
      view_mode: "floating",
      status: "open",
      live_dispatched: false,
      merge_executed: false,
      notes: [],
      authority: "operator_spawn_only",
    };
    const c = composeFloatingFullscreenOpen({
      session_id: "sess-2",
      parent_asset_id: "asset-1",
      existing_instance: existing,
      operator_ack: true,
    });
    expect(c.instance.instance_id).toBe("fdr_existing");
    expect(c.instance.view_mode).toBe("fullscreen");
    expect(c.fullscreen_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
  });

  it("gated highlight cannot spawn", () => {
    expect(() =>
      composeFloatingFullscreenOpen({
        session_id: "s",
        parent_asset_id: "a",
        highlight: "secret",
        gated: true,
        operator_ack: true,
      }),
    ).toThrow(/gated/);
  });

  it("operator_ack false blocks fullscreen_ready", () => {
    const c = composeFloatingFullscreenOpen({
      session_id: "sess-3",
      parent_asset_id: "asset-1",
      highlight: "open claim",
      gated: false,
      operator_ack: false,
    });
    // view mode may still apply; tray may need ack depending on action
    expect(c.fullscreen_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
  });

  it("closed existing instance rejected", () => {
    const existing: FloatingDeepResearchInstance = {
      instance_id: "fdr_closed",
      parent_asset_id: "asset-1",
      highlight: "done",
      prompt: "p",
      view_mode: "floating",
      status: "closed",
      live_dispatched: false,
      merge_executed: false,
      notes: [],
      authority: "operator_spawn_only",
    };
    expect(() =>
      composeFloatingFullscreenOpen({
        session_id: "s",
        parent_asset_id: "asset-1",
        existing_instance: existing,
        operator_ack: true,
      }),
    ).toThrow(/closed/);
  });

  it("spawn requires gated boolean", () => {
    expect(() =>
      composeFloatingFullscreenOpen({
        session_id: "s",
        parent_asset_id: "a",
        highlight: "h",
        operator_ack: true,
      }),
    ).toThrow(/gated/);
  });
});
