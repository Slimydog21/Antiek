import { describe, expect, it } from "vitest";
import {
  composeMidnightOilSourceAttachQuality,
  formatMidnightOilSourceAttachQualitySummary,
} from "./midnightOilSourceAttachQualityCompose";

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

describe("composeMidnightOilSourceAttachQuality", () => {
  it("MO + sources ready without live execution", () => {
    const c = composeMidnightOilSourceAttachQuality({
      operator_id: "op-1",
      work_minutes: 120,
      goals: [
        { goal_id: "g1", title: "Survey arxiv scaling laws" },
        { goal_id: "g2", title: "Synthesize substack claims" },
      ],
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
    expect(c.mo_unattended.unattended_package_ready).toBe(true);
    expect(c.source_quality.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.remote_fetched).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe(
      "midnight_oil_source_attach_quality_compose_advisory",
    );
    expect(formatMidnightOilSourceAttachQualitySummary(c)).toMatch(
      /live_execution_authorized=false/,
    );
  });

  it("blocks without unattended ack", () => {
    const c = composeMidnightOilSourceAttachQuality({
      operator_id: "op-1",
      work_minutes: 60,
      goals: [{ goal_id: "g1", title: "T" }],
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
    expect(c.mo_unattended.unattended_package_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("low source quality blocks pack", () => {
    const c = composeMidnightOilSourceAttachQuality({
      operator_id: "op-1",
      work_minutes: 120,
      goals: [{ goal_id: "g1", title: "Survey" }],
      usd_per_hour: 15,
      approved_ceiling_usd: 40,
      operator_ack: true,
      unattended_ack: true,
      spend_consent: true,
      session_id: "s",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      sources: [sources[0]],
      quality_overall: 0.2,
      quality_floor: 0.7,
      would_exceed: false,
    });
    expect(c.source_quality.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.remote_fetched).toBe(false);
  });

  it("budget would_exceed blocks source pack", () => {
    const c = composeMidnightOilSourceAttachQuality({
      operator_id: "op-1",
      work_minutes: 60,
      goals: [{ goal_id: "g1", title: "T" }],
      usd_per_hour: 10,
      approved_ceiling_usd: 20,
      operator_ack: true,
      unattended_ack: true,
      spend_consent: true,
      session_id: "s",
      parent_asset_id: "a",
      requested_families: ["arxiv"],
      sources: [sources[0]],
      quality_overall: 0.9,
      would_exceed: true,
    });
    expect(c.source_quality.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });
});
