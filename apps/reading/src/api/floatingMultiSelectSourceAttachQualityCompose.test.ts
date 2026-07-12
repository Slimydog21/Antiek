import { describe, expect, it } from "vitest";
import {
  composeFloatingMultiSelectSourceAttachQuality,
  formatFloatingMultiSelectSourceAttachQualitySummary,
} from "./floatingMultiSelectSourceAttachQualityCompose";

const members = [
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

const sources = [
  {
    source_id: "arx-1",
    family: "arxiv" as const,
    title: "Scaling Laws for Neural Language Models",
    external_id: "arxiv:2001.08361",
    html_fragment: "<article>abstract…</article>",
  },
  {
    source_id: "sub-1",
    family: "substack" as const,
    title: "Deep research essay",
    html_fragment: "<article>essay…</article>",
  },
];

describe("composeFloatingMultiSelectSourceAttachQuality", () => {
  it("multi-select + sources ready", () => {
    const c = composeFloatingMultiSelectSourceAttachQuality({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Synthesize A and B with arxiv/substack",
      operator_ack: true,
      requested_families: ["arxiv", "substack"],
      sources,
      quality_overall: 0.88,
      quality_floor: 0.7,
      would_exceed: false,
    });
    expect(c.multi_select.pack_ready).toBe(true);
    expect(c.source_quality.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.analysis_written).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.authority).toBe(
      "floating_multi_select_source_attach_quality_compose_advisory",
    );
    expect(formatFloatingMultiSelectSourceAttachQualitySummary(c)).toMatch(
      /remote_fetched=false/,
    );
  });

  it("budget would_exceed blocks source pack", () => {
    const c = composeFloatingMultiSelectSourceAttachQuality({
      session_id: "sess-2",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Go",
      operator_ack: true,
      requested_families: ["arxiv"],
      sources: [sources[0]],
      quality_overall: 0.9,
      would_exceed: true,
    });
    expect(c.source_quality.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeFloatingMultiSelectSourceAttachQuality({
      session_id: "sess-3",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b"],
      pack_mode: "cohesive_prompt",
      cohesive_prompt: "Synthesize",
      operator_ack: false,
      requested_families: ["arxiv", "substack"],
      sources,
      quality_overall: 0.9,
      would_exceed: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.remote_fetched).toBe(false);
  });

  it("low quality blocks", () => {
    const c = composeFloatingMultiSelectSourceAttachQuality({
      session_id: "sess-4",
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["inst-a", "inst-b", "inst-c"],
      pack_mode: "collective_pack",
      cohesive_prompt: "Pack",
      operator_ack: true,
      requested_families: ["arxiv"],
      sources: [sources[0]],
      quality_overall: 0.2,
      quality_floor: 0.7,
      would_exceed: false,
    });
    expect(c.source_quality.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
  });
});
