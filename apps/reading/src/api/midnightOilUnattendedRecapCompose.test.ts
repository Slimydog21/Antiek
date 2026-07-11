import { describe, expect, it } from "vitest";
import {
  composeMidnightOilUnattendedRecap,
  formatMidnightOilUnattendedRecapSummary,
} from "./midnightOilUnattendedRecapCompose";

describe("composeMidnightOilUnattendedRecap", () => {
  it("recap ready without re-authorizing execution", () => {
    const c = composeMidnightOilUnattendedRecap({
      run_id: "mo-1",
      operator_id: "op-1",
      work_minutes_planned: 120,
      work_minutes_actual: 110,
      price_ceiling_usd: 25,
      spend_usd: 18.5,
      operator_ack: true,
      artifact_ids: ["art-1"],
      goals: [
        { goal_id: "g1", title: "Survey arxiv", status: "done" },
        { goal_id: "g2", title: "Draft notes", status: "blocked" },
        { goal_id: "g3", title: "Follow-ups", status: "pending" },
      ],
    });
    expect(c.recap_ready).toBe(true);
    expect(c.goals_done).toBe(1);
    expect(c.goals_blocked).toBe(1);
    expect(c.within_ceiling).toBe(true);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.authority).toBe(
      "midnight_oil_unattended_recap_compose_advisory",
    );
    expect(formatMidnightOilUnattendedRecapSummary(c)).toMatch(
      /live_execution_authorized=false/,
    );
  });

  it("unknown spend leaves within_ceiling null", () => {
    const c = composeMidnightOilUnattendedRecap({
      run_id: "mo-1",
      operator_id: "op",
      work_minutes_planned: 60,
      work_minutes_actual: null,
      price_ceiling_usd: 10,
      spend_usd: null,
      operator_ack: true,
      goals: [{ goal_id: "g1", title: "T", status: "done" }],
    });
    expect(c.within_ceiling).toBeNull();
    expect(c.recap_ready).toBe(true);
    expect(c.live_execution_authorized).toBe(false);
  });

  it("not ready without ack or progress", () => {
    const noAck = composeMidnightOilUnattendedRecap({
      run_id: "mo",
      operator_id: "op",
      work_minutes_planned: 30,
      work_minutes_actual: 10,
      price_ceiling_usd: null,
      spend_usd: null,
      operator_ack: false,
      goals: [{ goal_id: "g1", title: "T", status: "done" }],
    });
    expect(noAck.recap_ready).toBe(false);

    const noProgress = composeMidnightOilUnattendedRecap({
      run_id: "mo",
      operator_id: "op",
      work_minutes_planned: 30,
      work_minutes_actual: 10,
      price_ceiling_usd: null,
      spend_usd: null,
      operator_ack: true,
      goals: [{ goal_id: "g1", title: "T", status: "pending" }],
    });
    expect(noProgress.recap_ready).toBe(false);
  });

  it("rejects empty goals and bad status", () => {
    expect(() =>
      composeMidnightOilUnattendedRecap({
        run_id: "mo",
        operator_id: "op",
        work_minutes_planned: 10,
        work_minutes_actual: null,
        price_ceiling_usd: null,
        spend_usd: null,
        operator_ack: true,
        goals: [],
      }),
    ).toThrow(/goals/);
    expect(() =>
      composeMidnightOilUnattendedRecap({
        run_id: "mo",
        operator_id: "op",
        work_minutes_planned: 10,
        work_minutes_actual: null,
        price_ceiling_usd: null,
        spend_usd: null,
        operator_ack: true,
        goals: [
          {
            goal_id: "g1",
            title: "T",
            // @ts-expect-error intentional
            status: "teleport",
          },
        ],
      }),
    ).toThrow(/status/);
  });
});
