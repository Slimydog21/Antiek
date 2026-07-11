import { describe, expect, it } from "vitest";
import {
  composeWorkstationRecordPromptModelDecision,
  formatWorkstationRecordPromptModelDecisionSummary,
} from "./workstationRecordPromptModelDecisionCompose";

const MODELS = [
  {
    model_id: "gpt-5",
    tier: "frontier",
    projected_cost_usd_high: 2,
    projected_cost_usd_low: 1,
  },
  {
    model_id: "composer-2.5",
    tier: "workhorse",
    projected_cost_usd_high: 0.5,
  },
];

const RECORDS = [
  {
    record_id: "r1",
    kind: "insight" as const,
    body: "scaling holds under noise",
    source_ref: "paper-1",
  },
  {
    record_id: "r2",
    kind: "question" as const,
    body: "What is the failure mode?",
  },
];

describe("composeWorkstationRecordPromptModelDecision", () => {
  it("pack ready with records, bridge, and model decision", () => {
    const c = composeWorkstationRecordPromptModelDecision({
      session_id: "sess-1",
      parent_asset_id: "paper-1",
      records: RECORDS,
      user_prompt: "Summarize open questions",
      selected_model_id: "gpt-5",
      models: MODELS,
      daily_cap_usd: 100,
      spent_usd: 40,
      projected_cost_usd_high: 2,
      projected_cost_usd_low: 1,
      operator_ack: true,
    });
    expect(c.pack_ready).toBe(true);
    expect(c.records.record_ready).toBe(true);
    expect(c.bridge.bridge_ready).toBe(true);
    expect(c.decision.decision_ready).toBe(true);
    expect(c.proposed_prompt).toMatch(/Workstation recursive context/);
    expect(c.proposed_prompt).toMatch(/Summarize open questions/);
    expect(c.usage_percent).toBe(40);
    expect(c.would_exceed).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(c.secrets_stored).toBe(false);
    expect(c.live_meter_read).toBe(false);
    expect(c.authority).toBe(
      "workstation_record_prompt_model_decision_compose_advisory",
    );
    const s = formatWorkstationRecordPromptModelDecisionSummary(c);
    expect(s).toMatch(/prompts_injected=false/);
    expect(s).toMatch(/live_router_authorized=false/);
  });

  it("would_exceed true when projected high exceeds remaining", () => {
    const c = composeWorkstationRecordPromptModelDecision({
      session_id: "s",
      parent_asset_id: "p",
      records: RECORDS,
      user_prompt: "Go deep",
      selected_model_id: "gpt-5",
      models: MODELS,
      daily_cap_usd: 10,
      spent_usd: 9,
      projected_cost_usd_high: 5,
      operator_ack: true,
    });
    expect(c.would_exceed).toBe(true);
    expect(c.pack_ready).toBe(true); // decision still ready; exceed is advisory
    expect(c.prompts_injected).toBe(false);
  });

  it("ack false not pack ready", () => {
    const c = composeWorkstationRecordPromptModelDecision({
      session_id: "s",
      parent_asset_id: "p",
      records: RECORDS,
      user_prompt: "Go",
      selected_model_id: "gpt-5",
      models: MODELS,
      daily_cap_usd: 100,
      spent_usd: 10,
      operator_ack: false,
    });
    expect(c.records.record_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.record_persisted).toBe(false);
  });

  it("maps claim/data to finding in bridge pack", () => {
    const c = composeWorkstationRecordPromptModelDecision({
      session_id: "s",
      parent_asset_id: "p",
      records: [
        { record_id: "c1", kind: "claim", body: "X implies Y" },
        { record_id: "d1", kind: "data", body: "n=42" },
      ],
      user_prompt: "Assess",
      selected_model_id: "composer-2.5",
      models: MODELS,
      daily_cap_usd: 50,
      spent_usd: 5,
      projected_cost_usd_high: 0.5,
      operator_ack: true,
    });
    expect(c.pack_ready).toBe(true);
    expect(c.bridge.proposed_prompt).toMatch(/X implies Y/);
    expect(c.bridge.proposed_prompt).toMatch(/n=42/);
  });

  it("rejects unknown selected model", () => {
    expect(() =>
      composeWorkstationRecordPromptModelDecision({
        session_id: "s",
        parent_asset_id: "p",
        records: RECORDS,
        user_prompt: "Go",
        selected_model_id: "nope",
        models: MODELS,
        daily_cap_usd: 10,
        spent_usd: 1,
        operator_ack: true,
      }),
    ).toThrow(/not found/);
  });
});
