import { describe, expect, it } from "vitest";
import {
  composeFloatingMultiSelectSourceAttachQualityTwin,
  formatFloatingMultiSelectSourceAttachQualityTwinSummary,
} from "./floatingMultiSelectSourceAttachQualityTwinCompose";

const members = [
  {
    instance_id: "inst-a",
    parent_asset_id: "asset-1",
    status: "open" as const,
    highlight: "scaling laws claim",
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

describe("composeFloatingMultiSelectSourceAttachQualityTwin", () => {
  it("multi-source + twin ready", () => {
    const c = composeFloatingMultiSelectSourceAttachQualityTwin({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Synthesize with sources",
      operator_ack: true,
      requested_families: ["arxiv"],
      sources,
      quality_overall: 0.9,
      would_exceed: false,
    });
    expect(c.multi_source.pack_ready).toBe(true);
    expect(c.twin_feed.feed_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    // 1 source + 2 members + cohesive prompt
    expect(c.twin_feed.finding_count).toBe(4);
    expect(c.live_dispatched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(
      formatFloatingMultiSelectSourceAttachQualityTwinSummary(c),
    ).toMatch(/twin_written=false/);
  });

  it("budget blocks multi_source pack", () => {
    const c = composeFloatingMultiSelectSourceAttachQualityTwin({
      session_id: "sess-2",
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
    expect(c.multi_source.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.twin_written).toBe(false);
  });

  it("operator_ack false", () => {
    const c = composeFloatingMultiSelectSourceAttachQualityTwin({
      session_id: "sess-3",
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
    expect(c.prompts_injected).toBe(false);
  });

  it("caller twin_findings", () => {
    const c = composeFloatingMultiSelectSourceAttachQualityTwin({
      session_id: "sess-4",
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
      twin_findings: [
        { source_id: "c1", body: "Caller collective insight", kind: "insight" },
      ],
    });
    expect(c.twin_feed.finding_count).toBe(1);
    expect(c.pack_ready).toBe(true);
    expect(c.twin_written).toBe(false);
  });
});
