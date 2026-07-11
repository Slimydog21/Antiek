import { describe, expect, it } from "vitest";
import {
  composeAntiekBenchWeeklyUsageLearn,
  formatAntiekBenchWeeklyUsageLearnSummary,
} from "./antiekBenchWeeklyUsageLearnCompose";

describe("composeAntiekBenchWeeklyUsageLearn", () => {
  it("proposes rewrites without mutating backlog/store", () => {
    const c = composeAntiekBenchWeeklyUsageLearn({
      week_id: "2026-W28",
      operator_ack: true,
      min_events_per_task: 2,
      events: [
        {
          event_id: "e1",
          task: "deep_research",
          model_id: "gpt-5",
          outcome: "failed",
        },
        {
          event_id: "e2",
          task: "deep_research",
          model_id: "gpt-5",
          outcome: "failed",
        },
        {
          event_id: "e3",
          task: "twin_notes",
          model_id: "claude",
          outcome: "worked",
        },
        {
          event_id: "e4",
          task: "twin_notes",
          model_id: "claude",
          outcome: "worked",
        },
      ],
    });
    expect(c.learn_ready).toBe(true);
    expect(c.proposal_count).toBe(2);
    expect(c.backlog_mutated).toBe(false);
    expect(c.store_mutated).toBe(false);
    const dr = c.proposals.find((p) => p.task === "deep_research");
    expect(dr?.emphasis).toBe("expand_failure_cases");
    const tn = c.proposals.find((p) => p.task === "twin_notes");
    expect(tn?.emphasis).toBe("hold_stable");
    expect(formatAntiekBenchWeeklyUsageLearnSummary(c)).toMatch(
      /backlog_mutated=false/,
    );
  });

  it("not ready without ack or below min events", () => {
    const noAck = composeAntiekBenchWeeklyUsageLearn({
      week_id: "w",
      operator_ack: false,
      min_events_per_task: 2,
      events: [
        {
          event_id: "e1",
          task: "t",
          model_id: "m",
          outcome: "failed",
        },
        {
          event_id: "e2",
          task: "t",
          model_id: "m",
          outcome: "failed",
        },
      ],
    });
    expect(noAck.learn_ready).toBe(false);

    const sparse = composeAntiekBenchWeeklyUsageLearn({
      week_id: "w",
      operator_ack: true,
      min_events_per_task: 5,
      events: [
        {
          event_id: "e1",
          task: "t",
          model_id: "m",
          outcome: "worked",
        },
      ],
    });
    expect(sparse.proposal_count).toBe(0);
    expect(sparse.learn_ready).toBe(false);
    expect(sparse.backlog_mutated).toBe(false);
  });

  it("rejects duplicate event ids and bad outcomes", () => {
    expect(() =>
      composeAntiekBenchWeeklyUsageLearn({
        week_id: "w",
        operator_ack: true,
        events: [
          {
            event_id: "e1",
            task: "t",
            model_id: "m",
            outcome: "worked",
          },
          {
            event_id: "e1",
            task: "t",
            model_id: "m",
            outcome: "failed",
          },
        ],
      }),
    ).toThrow(/duplicate/);
  });
});
