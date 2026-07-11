import { describe, expect, it } from "vitest";
import {
  composeFloatingMultiSelectCollectiveCohesive,
  formatFloatingMultiSelectCollectiveCohesiveSummary,
} from "./floatingMultiSelectCollectiveCohesiveCompose";

const baseMembers = [
  {
    instance_id: "inst-a",
    parent_asset_id: "asset-1",
    status: "open" as const,
    highlight: "scaling laws claim",
    prior_prompt: "What evidence supports the claim?",
    context: ["card-a"],
  },
  {
    instance_id: "inst-b",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    highlight: "counter-evidence",
    findings: ["finding-b1"],
  },
  {
    instance_id: "inst-c",
    parent_asset_id: "asset-1",
    status: "proposed" as const,
    highlight: "third angle",
  },
];

describe("composeFloatingMultiSelectCollectiveCohesive", () => {
  it("cohesive_prompt multi-select ready", () => {
    const c = composeFloatingMultiSelectCollectiveCohesive({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      members: baseMembers,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Synthesize A and B as one unit",
      operator_ack: true,
      extra_context: ["operator note"],
    });
    expect(c.tray.tray_ready).toBe(true);
    expect(c.cohesive?.pack_ready).toBe(true);
    expect(c.cohesive?.member_count).toBe(2);
    expect(c.analysis).toBeNull();
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.pack_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.authority).toBe(
      "floating_multi_select_collective_cohesive_compose_advisory",
    );
    expect(formatFloatingMultiSelectCollectiveCohesiveSummary(c)).toMatch(
      /pack_dispatched=false/,
    );
  });

  it("collective_pack multi-select ready without cohesive object", () => {
    const c = composeFloatingMultiSelectCollectiveCohesive({
      session_id: "sess-2",
      parent_asset_id: "asset-1",
      members: baseMembers,
      selected_instance_ids: ["inst-a", "inst-b", "inst-c"],
      pack_mode: "collective_pack",
      cohesive_prompt: "Run as pack",
      operator_ack: true,
    });
    expect(c.tray.action).toBe("collective_pack");
    expect(c.tray.selected_count).toBe(3);
    expect(c.cohesive).toBeNull();
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
  });

  it("cohesive_plus_analysis draft ready", () => {
    const c = composeFloatingMultiSelectCollectiveCohesive({
      session_id: "sess-3",
      parent_asset_id: "asset-1",
      members: baseMembers,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_plus_analysis",
      cohesive_prompt: "Merge findings into draft analysis",
      operator_ack: true,
      analysis_kind: "draft_analysis",
      extra_findings: ["operator synthesis note"],
    });
    expect(c.cohesive?.pack_ready).toBe(true);
    expect(c.analysis?.kind).toBe("draft_analysis");
    expect(c.analysis?.analysis_written).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.pack_ready).toBe(true);
  });

  it("full_analysis blocked until all selected completed", () => {
    const c = composeFloatingMultiSelectCollectiveCohesive({
      session_id: "sess-4",
      parent_asset_id: "asset-1",
      members: baseMembers,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_plus_analysis",
      cohesive_prompt: "Full merge analysis",
      operator_ack: true,
      analysis_kind: "full_analysis",
    });
    // inst-a is open — soft-gate: no full analysis intent, pack not ready
    expect(c.analysis).toBeNull();
    expect(c.pack_ready).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("full_analysis ready when all completed + ack", () => {
    const members = [
      {
        instance_id: "x",
        parent_asset_id: "p",
        status: "completed" as const,
        findings: ["fx"],
      },
      {
        instance_id: "y",
        parent_asset_id: "p",
        status: "completed" as const,
        findings: ["fy"],
      },
    ];
    const c = composeFloatingMultiSelectCollectiveCohesive({
      session_id: "sess-5",
      parent_asset_id: "p",
      members,
      selected_instance_ids: ["x", "y"],
      pack_mode: "cohesive_plus_analysis",
      cohesive_prompt: "Full unit analysis",
      operator_ack: true,
      analysis_kind: "full_analysis",
    });
    expect(c.pack_ready).toBe(true);
    expect(c.analysis?.kind).toBe("full_analysis");
    expect(c.analysis_written).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("operator_ack false blocks pack_ready", () => {
    const c = composeFloatingMultiSelectCollectiveCohesive({
      session_id: "sess-6",
      parent_asset_id: "asset-1",
      members: baseMembers,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Need ack",
      operator_ack: false,
    });
    expect(c.tray.tray_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("rejects single select", () => {
    expect(() =>
      composeFloatingMultiSelectCollectiveCohesive({
        session_id: "s",
        parent_asset_id: "asset-1",
        members: baseMembers,
        selected_instance_ids: ["inst-a"],
        pack_mode: "cohesive_prompt",
        cohesive_prompt: "solo",
        operator_ack: true,
      }),
    ).toThrow(/at least 2/);
  });
});
