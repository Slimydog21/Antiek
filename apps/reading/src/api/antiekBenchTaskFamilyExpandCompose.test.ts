import { describe, expect, it } from "vitest";
import {
  composeAntiekBenchTaskFamilyExpand,
  formatAntiekBenchTaskFamilyExpandSummary,
} from "./antiekBenchTaskFamilyExpandCompose";

describe("composeAntiekBenchTaskFamilyExpand", () => {
  it("proposes expand for new families and usage failures", () => {
    const c = composeAntiekBenchTaskFamilyExpand({
      week_id: "2026-W28",
      existing_tasks: ["deep_research", "twin_notes"],
      proposed_new_tasks: [
        { task: "marketplace_port", description: "HTML book host quality" },
      ],
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
          task: "deep_research",
          model_id: "composer",
          outcome: "failed",
        },
        {
          event_id: "e4",
          task: "twin_notes",
          model_id: "gpt-5",
          outcome: "worked",
        },
        {
          event_id: "e5",
          task: "twin_notes",
          model_id: "gpt-5",
          outcome: "worked",
        },
        {
          event_id: "e6",
          task: "twin_notes",
          model_id: "gpt-5",
          outcome: "worked",
        },
      ],
      operator_ack: true,
      min_events_per_task: 3,
    });
    expect(c.expand_ready).toBe(true);
    expect(c.new_proposed_count).toBe(1);
    expect(c.backlog_mutated).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.suite_rewritten).toBe(false);
    expect(c.families.some((f) => f.task === "marketplace_port")).toBe(true);
    expect(c.authority).toBe(
      "antiek_bench_task_family_expand_compose_advisory",
    );
    const s = formatAntiekBenchTaskFamilyExpandSummary(c);
    expect(s).toMatch(/suite_rewritten=false/);
    expect(s).toMatch(/backlog_mutated=false/);
  });

  it("ack false not expand_ready", () => {
    const c = composeAntiekBenchTaskFamilyExpand({
      week_id: "w",
      existing_tasks: ["deep_research"],
      proposed_new_tasks: [{ task: "chase_swarm" }],
      events: [],
      operator_ack: false,
    });
    expect(c.expand_ready).toBe(false);
    expect(c.suite_rewritten).toBe(false);
  });

  it("no expand when nothing new and no learn signal", () => {
    const c = composeAntiekBenchTaskFamilyExpand({
      week_id: "w",
      existing_tasks: ["deep_research"],
      events: [
        {
          event_id: "e1",
          task: "deep_research",
          model_id: "m",
          outcome: "worked",
        },
      ],
      operator_ack: true,
      min_events_per_task: 3,
    });
    expect(c.expand_ready).toBe(false);
    expect(c.suite_rewritten).toBe(false);
  });

  it("rejects duplicate existing tasks", () => {
    expect(() =>
      composeAntiekBenchTaskFamilyExpand({
        week_id: "w",
        existing_tasks: ["a", "a"],
        events: [],
        operator_ack: true,
      }),
    ).toThrow(/duplicate/);
  });
});
