import { describe, expect, it } from "vitest";
import {
  formatFloatingSummary,
  markFloatingCompleted,
  proposeCollectivePack,
  proposeDraftMerge,
  proposeFullMerge,
  setFloatingViewMode,
  spawnFloatingFromHighlight,
} from "./floatingDeepResearch";

describe("spawnFloatingFromHighlight", () => {
  it("spawns floating instance with fail-closed flags", () => {
    const inst = spawnFloatingFromHighlight({
      parent_asset_id: "asset-1",
      highlight: "scaling laws hold under compute constraints",
      gated: false,
    });
    expect(inst.parent_asset_id).toBe("asset-1");
    expect(inst.view_mode).toBe("floating");
    expect(inst.live_dispatched).toBe(false);
    expect(inst.merge_executed).toBe(false);
    expect(inst.authority).toBe("operator_spawn_only");
    expect(inst.status).toBe("proposed");
  });

  it("rejects gated highlight", () => {
    expect(() =>
      spawnFloatingFromHighlight({
        parent_asset_id: "a",
        highlight: "secret",
        gated: true,
      }),
    ).toThrow(/gated/);
  });

  it("rejects missing gated", () => {
    expect(() =>
      spawnFloatingFromHighlight({
        parent_asset_id: "a",
        highlight: "x",
        // @ts-expect-error intentional
        gated: undefined,
      }),
    ).toThrow(/gated/);
  });

  it("rejects empty highlight", () => {
    expect(() =>
      spawnFloatingFromHighlight({
        parent_asset_id: "a",
        highlight: "  ",
        gated: false,
      }),
    ).toThrow(/highlight/);
  });

  it("rejects spawn as merged", () => {
    expect(() =>
      spawnFloatingFromHighlight({
        parent_asset_id: "a",
        highlight: "h",
        gated: false,
        view_mode: "merged_full",
      }),
    ).toThrow(/merge/);
  });
});

describe("view mode and completion", () => {
  it("sets fullscreen and marks completed without dispatch", () => {
    let inst = spawnFloatingFromHighlight({
      parent_asset_id: "a",
      highlight: "h",
      gated: false,
    });
    inst = setFloatingViewMode(inst, "fullscreen");
    expect(inst.view_mode).toBe("fullscreen");
    expect(inst.status).toBe("open");
    inst = markFloatingCompleted(inst);
    expect(inst.status).toBe("completed");
    expect(inst.live_dispatched).toBe(false);
  });
});

describe("merge intents", () => {
  it("draft merge never executes", () => {
    let inst = spawnFloatingFromHighlight({
      parent_asset_id: "a",
      highlight: "h",
      gated: false,
    });
    inst = setFloatingViewMode(inst, "floating");
    const intent = proposeDraftMerge(inst);
    expect(intent.kind).toBe("draft_merge");
    expect(intent.merge_executed).toBe(false);
    expect(intent.operator_ack).toBe(false);
  });

  it("full merge requires ack and completed", () => {
    let inst = spawnFloatingFromHighlight({
      parent_asset_id: "a",
      highlight: "h",
      gated: false,
    });
    expect(() =>
      proposeFullMerge(inst, { operator_ack: true }),
    ).toThrow(/completed/);
    inst = markFloatingCompleted(setFloatingViewMode(inst, "floating"));
    expect(() =>
      proposeFullMerge(inst, { operator_ack: false }),
    ).toThrow(/operator_ack/);
    const intent = proposeFullMerge(inst, { operator_ack: true });
    expect(intent.merge_executed).toBe(false);
    expect(intent.operator_ack).toBe(true);
  });
});

describe("collective pack", () => {
  it("requires ≥2 same-parent instances", () => {
    const a = markFloatingCompleted(
      setFloatingViewMode(
        spawnFloatingFromHighlight({
          parent_asset_id: "p",
          highlight: "one",
          gated: false,
        }),
        "floating",
      ),
    );
    const b = markFloatingCompleted(
      setFloatingViewMode(
        spawnFloatingFromHighlight({
          parent_asset_id: "p",
          highlight: "two different",
          gated: false,
        }),
        "floating",
      ),
    );
    expect(() => proposeCollectivePack([a])).toThrow(/at least 2/);
    const pack = proposeCollectivePack([a, b]);
    expect(pack.pack_dispatched).toBe(false);
    expect(pack.instance_ids).toHaveLength(2);
    expect(pack.parent_asset_id).toBe("p");
  });

  it("rejects cross-parent pack", () => {
    const a = markFloatingCompleted(
      setFloatingViewMode(
        spawnFloatingFromHighlight({
          parent_asset_id: "p1",
          highlight: "one",
          gated: false,
        }),
        "floating",
      ),
    );
    const b = markFloatingCompleted(
      setFloatingViewMode(
        spawnFloatingFromHighlight({
          parent_asset_id: "p2",
          highlight: "two",
          gated: false,
        }),
        "floating",
      ),
    );
    expect(() => proposeCollectivePack([a, b])).toThrow(/same parent/);
  });
});

describe("formatFloatingSummary", () => {
  it("summarizes honesty flags", () => {
    const inst = spawnFloatingFromHighlight({
      parent_asset_id: "a",
      highlight: "h",
      gated: false,
    });
    expect(formatFloatingSummary(inst)).toMatch(/live_dispatched=false/);
  });
});
