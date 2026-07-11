import { describe, expect, it } from "vitest";
import {
  composeRecursiveTwinSearchPromptContext,
  formatRecursiveTwinSearchPromptContextSummary,
} from "./recursiveTwinSearchPromptContextCompose";

const models = [
  { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
  { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
];

const twinRecords = [
  {
    twin_id: "twin-1",
    parent_asset_id: "asset-1",
    insights: ["scaling laws hold under compute-optimal regimes"],
    questions: ["Does the law break at sparse models?"],
    source_label: "paper-notes",
  },
  {
    twin_id: "twin-2",
    parent_asset_id: "asset-2",
    insights: ["attention efficiency tradeoffs"],
    questions: ["What is the scaling frontier?"],
  },
];

describe("composeRecursiveTwinSearchPromptContext", () => {
  it("twin propose + search hits + prompt pack ready", () => {
    const c = composeRecursiveTwinSearchPromptContext({
      session_id: "sess-1",
      parent_asset_id: "asset-1",
      source_excerpt: "Parent document about neural scaling laws.",
      focus_questions: ["What is the core claim?"],
      twin_records: twinRecords,
      search_query: "scaling laws",
      user_prompt: "Synthesize twin insights for next research step",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 20,
      spent_usd: 3,
      projected_cost_usd_high: 0.4,
      operator_ack: true,
    });
    expect(c.twin_propose.twin_propose_ready).toBe(true);
    expect(c.search.hits.length).toBeGreaterThan(0);
    expect(c.prompt_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.twin_written).toBe(false);
    expect(c.remote_index_queried).toBe(false);
    expect(c.record_persisted).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(c.authority).toBe(
      "recursive_twin_search_prompt_context_compose_advisory",
    );
    expect(formatRecursiveTwinSearchPromptContextSummary(c)).toMatch(
      /prompts_injected=false/,
    );
  });

  it("no hits seeds excerpt scaffold for prompt pack", () => {
    const c = composeRecursiveTwinSearchPromptContext({
      session_id: "sess-2",
      parent_asset_id: "asset-x",
      source_excerpt: "Unrelated excerpt about gardens and soil.",
      twin_records: twinRecords,
      search_query: "zzzznonexistenttoken",
      user_prompt: "Continue",
      selected_model_id: "grok-4.5",
      models,
      daily_cap_usd: 10,
      spent_usd: 1,
      operator_ack: true,
    });
    expect(c.search.hits.length).toBe(0);
    expect(c.prompt_pack.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.remote_index_queried).toBe(false);
  });

  it("operator_ack false blocks pack_ready", () => {
    const c = composeRecursiveTwinSearchPromptContext({
      session_id: "sess-3",
      parent_asset_id: "asset-1",
      source_excerpt: "Source text",
      twin_records: twinRecords,
      search_query: "scaling",
      user_prompt: "Go",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 10,
      spent_usd: 0,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.prompts_injected).toBe(false);
  });

  it("budget honesty on prompt pack", () => {
    const c = composeRecursiveTwinSearchPromptContext({
      session_id: "sess-4",
      parent_asset_id: "asset-1",
      source_excerpt: "Scaling text",
      twin_records: twinRecords,
      search_query: "scaling",
      user_prompt: "Deep research next",
      selected_model_id: "gpt-5.5",
      models,
      daily_cap_usd: 1,
      spent_usd: 0.9,
      projected_cost_usd_high: 0.5,
      operator_ack: true,
    });
    expect(c.prompt_pack.would_exceed).toBe(true);
    expect(c.live_router_authorized).toBe(false);
  });
});
