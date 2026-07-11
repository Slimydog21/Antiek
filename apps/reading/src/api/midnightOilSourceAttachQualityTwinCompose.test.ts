import { describe, expect, it } from "vitest";
import {
  composeMidnightOilSourceAttachQualityTwin,
  formatMidnightOilSourceAttachQualityTwinSummary,
} from "./midnightOilSourceAttachQualityTwinCompose";

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

const goals = [
  { goal_id: "g1", title: "Survey arxiv scaling laws" },
  { goal_id: "g2", title: "Synthesize substack claims" },
];

describe("composeMidnightOilSourceAttachQualityTwin", () => {
  it("MO + sources + twin ready", () => {
    const c = composeMidnightOilSourceAttachQualityTwin({
      operator_id: "op-1",
      work_minutes: 120,
      goals,
      usd_per_hour: 15,
      approved_ceiling_usd: 40,
      operator_ack: true,
      unattended_ack: true,
      spend_consent: true,
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      requested_families: ["arxiv", "substack"],
      sources,
      quality_overall: 0.88,
      quality_floor: 0.7,
      would_exceed: false,
    });
    expect(c.mo_source.pack_ready).toBe(true);
    expect(c.twin_feed.feed_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.twin_feed.finding_count).toBe(4); // 2 sources + 2 goals
    expect(c.live_execution_authorized).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.authority).toBe(
      "midnight_oil_source_attach_quality_twin_compose_advisory",
    );
    expect(formatMidnightOilSourceAttachQualityTwinSummary(c)).toMatch(
      /twin_written=false/,
    );
  });

  it("blocks without unattended ack", () => {
    const c = composeMidnightOilSourceAttachQualityTwin({
      operator_id: "op-1",
      work_minutes: 60,
      goals: [goals[0]],
      usd_per_hour: 10,
      approved_ceiling_usd: 20,
      operator_ack: true,
      unattended_ack: false,
      spend_consent: true,
      session_id: "s",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      sources: [sources[0]],
      quality_overall: 0.9,
      would_exceed: false,
    });
    expect(c.mo_source.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("caller twin_findings", () => {
    const c = composeMidnightOilSourceAttachQualityTwin({
      operator_id: "op-1",
      work_minutes: 120,
      goals: [goals[0]],
      usd_per_hour: 15,
      approved_ceiling_usd: 40,
      operator_ack: true,
      unattended_ack: true,
      spend_consent: true,
      session_id: "s",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      sources: [sources[0]],
      quality_overall: 0.9,
      would_exceed: false,
      twin_findings: [
        {
          source_id: "custom-1",
          body: "Unattended recap insight",
          kind: "insight",
        },
      ],
    });
    expect(c.twin_feed.finding_count).toBe(1);
    expect(c.pack_ready).toBe(true);
    expect(c.twin_written).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeMidnightOilSourceAttachQualityTwin({
      operator_id: "op-1",
      work_minutes: 120,
      goals,
      usd_per_hour: 15,
      approved_ceiling_usd: 40,
      operator_ack: false,
      unattended_ack: true,
      spend_consent: true,
      session_id: "s",
      parent_asset_id: "a",
      requested_families: ["arxiv", "substack"],
      sources,
      quality_overall: 0.9,
      would_exceed: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.prompts_injected).toBe(false);
  });
});
