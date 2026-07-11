import { describe, expect, it } from "vitest";
import {
  bridgeHighlightToFloatingAndTwin,
  formatBridgeSummary,
} from "./highlightFloatingTwinBridge";

describe("bridgeHighlightToFloatingAndTwin", () => {
  it("spawns floating + twin bind with honesty flags", () => {
    const r = bridgeHighlightToFloatingAndTwin({
      parent_asset_id: "asset-1",
      highlight: "scaling laws hold under compute constraints",
      gated: false,
      insights: ["claim is load-bearing"],
      questions: ["what is the counterexample?"],
    });
    expect(r.live_dispatched).toBe(false);
    expect(r.twin_created).toBe(false);
    expect(r.floating.live_dispatched).toBe(false);
    expect(r.floating.view_mode).toBe("floating");
    expect(r.twin_bind.bind_allowed).toBe(true);
    expect(r.twin_bind.twin_created).toBe(false);
    expect(r.twin_bind.insights).toEqual(["claim is load-bearing"]);
    expect(r.authority).toBe("highlight_floating_twin_bridge_advisory");
  });

  it("rejects gated highlight", () => {
    expect(() =>
      bridgeHighlightToFloatingAndTwin({
        parent_asset_id: "a",
        highlight: "secret",
        gated: true,
      }),
    ).toThrow(/gated/);
  });

  it("requires explicit gated", () => {
    expect(() =>
      bridgeHighlightToFloatingAndTwin({
        parent_asset_id: "a",
        highlight: "h",
        // @ts-expect-error intentional
        gated: undefined,
      }),
    ).toThrow(/gated/);
  });

  it("empty scaffold twin allowed without inventing content", () => {
    const r = bridgeHighlightToFloatingAndTwin({
      parent_asset_id: "asset-1",
      highlight: "interesting claim",
      gated: false,
    });
    expect(r.twin_bind.insights).toEqual([]);
    expect(r.twin_bind.questions).toEqual([]);
    expect(r.twin_created).toBe(false);
  });

  it("llm path requires lists", () => {
    expect(() =>
      bridgeHighlightToFloatingAndTwin({
        parent_asset_id: "a",
        highlight: "h",
        gated: false,
        twin_source: "llm_note_taker",
        llm_filled: true,
      }),
    ).toThrow(/non-empty/);
  });
});

describe("formatBridgeSummary", () => {
  it("summarizes honesty", () => {
    const r = bridgeHighlightToFloatingAndTwin({
      parent_asset_id: "a",
      highlight: "h",
      gated: false,
    });
    expect(formatBridgeSummary(r)).toMatch(/live_dispatched=false/);
    expect(formatBridgeSummary(r)).toMatch(/twin_created=false/);
  });
});
