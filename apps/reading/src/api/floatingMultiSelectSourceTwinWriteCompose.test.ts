import { describe, expect, it } from "vitest";
import {
  composeFloatingMultiSelectSourceTwinWrite,
  formatFloatingMultiSelectSourceTwinWriteSummary,
} from "./floatingMultiSelectSourceTwinWriteCompose";

const members = [
  {
    instance_id: "inst-a",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    highlight: "scaling laws claim",
    findings: ["finding-a1"],
  },
  {
    instance_id: "inst-b",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    highlight: "counter-evidence",
    findings: ["finding-b1"],
  },
];

const sources = [
  {
    source_id: "arx-1",
    family: "arxiv" as const,
    title: "Scaling Laws for Neural Language Models",
    html_fragment: "<article>abstract…</article>",
  },
];

describe("composeFloatingMultiSelectSourceTwinWrite", () => {
  it("multi-twin + write pack ready", () => {
    const c = composeFloatingMultiSelectSourceTwinWrite({
      session_id: "sess-1",
      draft_id: "draft-1",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Synthesize with sources into write",
      operator_ack: true,
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      would_exceed: false,
    });
    expect(c.multi_twin.pack_ready).toBe(true);
    expect(c.write_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.draft_written).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.authority).toBe(
      "floating_multi_select_source_twin_write_compose_advisory",
    );
    expect(formatFloatingMultiSelectSourceTwinWriteSummary(c)).toMatch(
      /draft_written=false/,
    );
  });

  it("budget blocks multi_twin pack", () => {
    const c = composeFloatingMultiSelectSourceTwinWrite({
      session_id: "sess-2",
      draft_id: "draft-2",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Go",
      operator_ack: true,
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      would_exceed: true,
    });
    expect(c.multi_twin.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.draft_written).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeFloatingMultiSelectSourceTwinWrite({
      session_id: "sess-3",
      draft_id: "draft-3",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Synthesize",
      operator_ack: false,
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      would_exceed: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.analysis_written).toBe(false);
  });

  it("caller twin_slices override", () => {
    const c = composeFloatingMultiSelectSourceTwinWrite({
      session_id: "sess-4",
      draft_id: "draft-4",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Synthesize",
      operator_ack: true,
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      would_exceed: false,
      twin_slices: [
        {
          parent_asset_id: "asset-1",
          insights: ["Caller insight A", "Caller insight B"],
          questions: ["Q1?"],
        },
      ],
      chase_slots: [
        {
          slot_id: "s1",
          question_id: "q1",
          parent_asset_id: "asset-1",
          status: "completed",
          findings: ["f1"],
        },
        {
          slot_id: "s2",
          question_id: "q2",
          parent_asset_id: "asset-1",
          status: "completed",
          findings: ["f2"],
        },
      ],
      analysis_kind: "full_analysis",
    });
    expect(c.write_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.merge_executed).toBe(false);
  });
});
