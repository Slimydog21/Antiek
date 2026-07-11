import { describe, expect, it } from "vitest";
import {
  composeMidnightOilEntryToSwarmReadiness,
  formatMidnightOilEntryToSwarmReadinessSummary,
} from "./midnightOilEntryToSwarmReadinessCompose";

describe("composeMidnightOilEntryToSwarmReadiness", () => {
  it("package ready when entry + unattended gates pass", () => {
    const c = composeMidnightOilEntryToSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 120,
      goals: [
        { goal_id: "g1", title: "Survey arxiv" },
        { goal_id: "g2", title: "Draft notes" },
      ],
      usd_per_hour: 15,
      approved_ceiling_usd: 40,
      operator_ack: true,
      brief_dispatch_ready: true,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(c.entry.entry_ready).toBe(true);
    expect(c.readiness.unattended_ready).toBe(true);
    expect(c.package_ready).toBe(true);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.authority).toBe(
      "midnight_oil_entry_to_swarm_readiness_compose_advisory",
    );
    expect(formatMidnightOilEntryToSwarmReadinessSummary(c)).toMatch(
      /live_execution_authorized=false/,
    );
  });

  it("not package ready without unattended ack", () => {
    const c = composeMidnightOilEntryToSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 60,
      goals: [{ goal_id: "g1", title: "T" }],
      usd_per_hour: 10,
      approved_ceiling_usd: 20,
      operator_ack: true,
      brief_dispatch_ready: true,
      unattended_ack: false,
      spend_consent: true,
    });
    expect(c.package_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("not package ready without approved ceiling", () => {
    const c = composeMidnightOilEntryToSwarmReadiness({
      operator_id: "op-1",
      work_minutes: 60,
      goals: [{ goal_id: "g1", title: "T" }],
      usd_per_hour: 10,
      approved_ceiling_usd: null,
      operator_ack: true,
      brief_dispatch_ready: true,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(c.entry.entry_ready).toBe(false);
    expect(c.package_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });
});
