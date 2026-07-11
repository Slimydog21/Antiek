import { describe, expect, it } from "vitest";
import {
  composeFloatingDraftBeforeFullMergeGate,
  formatFloatingDraftBeforeFullMergeGateSummary,
} from "./floatingDraftBeforeFullMergeGateCompose";

describe("composeFloatingDraftBeforeFullMergeGate", () => {
  it("draft_only ready with single source", () => {
    const c = composeFloatingDraftBeforeFullMergeGate({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      parent_excerpt: "<p>Parent body</p>",
      sources: [
        {
          instance_id: "float-1",
          parent_asset_id: "asset-1",
          status: "completed",
          highlight: "key claim",
          findings: ["evidence A"],
        },
      ],
      stage: "draft_only",
      operator_ack: true,
    });
    expect(c.draft.draft_ready).toBe(true);
    expect(c.tray?.tray_ready).toBe(true);
    expect(c.gate_ready).toBe(true);
    expect(c.full_merge_intent_ready).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.authority).toBe(
      "floating_draft_before_full_merge_gate_compose_advisory",
    );
    expect(formatFloatingDraftBeforeFullMergeGateSummary(c)).toMatch(
      /merge_executed=false/,
    );
  });

  it("draft_only multi-source without tray full_merge", () => {
    const c = composeFloatingDraftBeforeFullMergeGate({
      session_id: "sess-2",
      parent_asset_id: "asset-1",
      sources: [
        {
          instance_id: "a",
          parent_asset_id: "asset-1",
          status: "open",
          highlight: "h1",
        },
        {
          instance_id: "b",
          parent_asset_id: "asset-1",
          status: "completed",
          findings: ["f2"],
        },
      ],
      stage: "draft_only",
      operator_ack: true,
    });
    expect(c.draft.draft_ready).toBe(true);
    expect(c.tray).toBeNull();
    expect(c.gate_ready).toBe(true);
    expect(c.merge_executed).toBe(false);
  });

  it("promote_full_merge requires full_merge_ack", () => {
    const c = composeFloatingDraftBeforeFullMergeGate({
      session_id: "sess-3",
      parent_asset_id: "asset-1",
      sources: [
        {
          instance_id: "float-1",
          parent_asset_id: "asset-1",
          status: "completed",
          findings: ["done"],
        },
      ],
      stage: "promote_full_merge",
      operator_ack: true,
      full_merge_ack: false,
    });
    expect(c.draft.draft_ready).toBe(true);
    expect(c.full_merge_intent_ready).toBe(false);
    expect(c.gate_ready).toBe(false);
    expect(c.merge_executed).toBe(false);
  });

  it("promote_full_merge ready when draft + dual ack + completed", () => {
    const c = composeFloatingDraftBeforeFullMergeGate({
      session_id: "sess-4",
      parent_asset_id: "asset-1",
      parent_excerpt: "parent",
      sources: [
        {
          instance_id: "float-1",
          parent_asset_id: "asset-1",
          status: "completed",
          highlight: "claim",
          findings: ["f1"],
        },
      ],
      stage: "promote_full_merge",
      operator_ack: true,
      full_merge_ack: true,
    });
    expect(c.full_merge_intent_ready).toBe(true);
    expect(c.gate_ready).toBe(true);
    expect(c.tray?.action).toBe("full_merge_one");
    expect(c.merge_executed).toBe(false);
    expect(c.draft_written).toBe(false);
  });

  it("promote blocked when sources not completed", () => {
    const c = composeFloatingDraftBeforeFullMergeGate({
      session_id: "sess-5",
      parent_asset_id: "asset-1",
      sources: [
        {
          instance_id: "float-1",
          parent_asset_id: "asset-1",
          status: "open",
          highlight: "still open",
        },
      ],
      stage: "promote_full_merge",
      operator_ack: true,
      full_merge_ack: true,
    });
    expect(c.full_merge_intent_ready).toBe(false);
    expect(c.gate_ready).toBe(false);
    expect(c.merge_executed).toBe(false);
  });

  it("draft_only without ack not gate_ready", () => {
    const c = composeFloatingDraftBeforeFullMergeGate({
      session_id: "sess-6",
      parent_asset_id: "asset-1",
      sources: [
        {
          instance_id: "float-1",
          parent_asset_id: "asset-1",
          status: "completed",
          findings: ["f"],
        },
      ],
      stage: "draft_only",
      operator_ack: false,
    });
    expect(c.draft.draft_ready).toBe(true);
    expect(c.gate_ready).toBe(false);
    expect(c.draft_written).toBe(false);
  });

  it("rejects promote without full_merge_ack boolean", () => {
    expect(() =>
      composeFloatingDraftBeforeFullMergeGate({
        session_id: "s",
        parent_asset_id: "a",
        sources: [
          {
            instance_id: "i",
            parent_asset_id: "a",
            status: "completed",
            findings: ["f"],
          },
        ],
        stage: "promote_full_merge",
        operator_ack: true,
      }),
    ).toThrow(/full_merge_ack/);
  });
});
