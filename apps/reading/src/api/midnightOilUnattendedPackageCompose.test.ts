import { describe, expect, it } from "vitest";
import {
  composeMidnightOilUnattendedPackage,
  formatMidnightOilUnattendedPackageSummary,
} from "./midnightOilUnattendedPackageCompose";

describe("composeMidnightOilUnattendedPackage", () => {
  it("full package ready without live execution", () => {
    const c = composeMidnightOilUnattendedPackage({
      operator_id: "op-1",
      work_minutes: 120,
      goals: [
        { goal_id: "g1", title: "Survey arxiv" },
        { goal_id: "g2", title: "Draft notes" },
      ],
      usd_per_hour: 15,
      approved_ceiling_usd: 40,
      operator_ack: true,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(c.entry_readiness.package_ready).toBe(true);
    expect(c.launch.package_ready).toBe(true);
    expect(c.unattended_package_ready).toBe(true);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.authority).toBe(
      "midnight_oil_unattended_package_compose_advisory",
    );
    expect(formatMidnightOilUnattendedPackageSummary(c)).toMatch(
      /live_execution_authorized=false/,
    );
  });

  it("blocks without unattended ack", () => {
    const c = composeMidnightOilUnattendedPackage({
      operator_id: "op-1",
      work_minutes: 60,
      goals: [{ goal_id: "g1", title: "T" }],
      usd_per_hour: 10,
      approved_ceiling_usd: 20,
      operator_ack: true,
      unattended_ack: false,
      spend_consent: true,
    });
    expect(c.unattended_package_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("blocks without approved ceiling", () => {
    const c = composeMidnightOilUnattendedPackage({
      operator_id: "op-1",
      work_minutes: 60,
      goals: [{ goal_id: "g1", title: "T" }],
      usd_per_hour: 10,
      approved_ceiling_usd: null,
      operator_ack: true,
      unattended_ack: true,
      spend_consent: true,
    });
    expect(c.entry_readiness.entry.entry_ready).toBe(false);
    expect(c.unattended_package_ready).toBe(false);
  });

  it("blocks without spend consent when ceiling > 0", () => {
    const c = composeMidnightOilUnattendedPackage({
      operator_id: "op-1",
      work_minutes: 60,
      goals: [{ goal_id: "g1", title: "T" }],
      usd_per_hour: 10,
      approved_ceiling_usd: 20,
      operator_ack: true,
      unattended_ack: true,
      spend_consent: false,
    });
    expect(c.unattended_package_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });
});
