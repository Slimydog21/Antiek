import { describe, expect, it } from "vitest";
import {
  composeMarketplaceHtmlTwinInterrogation,
  formatMarketplaceHtmlTwinInterrogationSummary,
} from "./marketplaceHtmlTwinInterrogationCompose";

const models = [
  { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
  { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
];

const questions = [
  {
    question_id: "q1",
    body: "What is the book's core thesis?",
    priority: 2,
  },
  {
    question_id: "q2",
    body: "Which claims need counter-evidence?",
    priority: 1,
  },
];

function freeMarketBase() {
  return {
    session_id: "sess-1",
    asset_id: "book-1",
    title: "Scaling Laws",
    account_id: "acct-1",
    free_copy_available: true,
    free_html_projection_sha: "sha-free",
    port_requested: true,
    purchase_ack: false,
    list_price_usd: 10 as number | null,
    approved_spend_usd: 20 as number | null,
    remaining_budget_usd: 50 as number | null,
    operator_ack: true,
    view_requested: true,
  };
}

describe("composeMarketplaceHtmlTwinInterrogation", () => {
  it("free HTML book + twin + interrogation ready", () => {
    const c = composeMarketplaceHtmlTwinInterrogation({
      ...freeMarketBase(),
      include_twin_feed: true,
      include_interrogation: true,
      questions,
      chase_mode: "swarm_fanout",
      models,
      selected_model_id: "gpt-5.5",
      daily_cap_usd: 25,
      spent_usd: 3,
      projected_cost_usd_high: 0.4,
      would_exceed: false,
      source_families: ["arxiv", "web"],
      user_prompt: "Interrogate this hosted HTML book",
    });
    expect(c.market_twin.session_ready).toBe(true);
    expect(c.interrogation?.loop_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.purchase_executed).toBe(false);
    expect(c.charge_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.prompts_injected).toBe(false);
    expect(c.live_router_authorized).toBe(false);
    expect(c.authority).toBe(
      "marketplace_html_twin_interrogation_compose_advisory",
    );
    expect(formatMarketplaceHtmlTwinInterrogationSummary(c)).toMatch(
      /pdf_view_authorized=false/,
    );
  });

  it("skip interrogation still pack_ready when market ready", () => {
    const c = composeMarketplaceHtmlTwinInterrogation({
      ...freeMarketBase(),
      include_interrogation: false,
    });
    expect(c.market_twin.session_ready).toBe(true);
    expect(c.interrogation).toBeNull();
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
  });

  it("budget block on market prevents pack_ready", () => {
    const c = composeMarketplaceHtmlTwinInterrogation({
      session_id: "s",
      asset_id: "b",
      title: "Expensive",
      account_id: "a",
      free_copy_available: false,
      purchase_html_projection_sha: "sha",
      port_requested: true,
      purchase_ack: true,
      list_price_usd: 50,
      approved_spend_usd: 60,
      remaining_budget_usd: 5,
      operator_ack: true,
      view_requested: true,
      include_interrogation: true,
      questions,
      models,
      selected_model_id: "gpt-5.5",
      daily_cap_usd: 20,
      spent_usd: 1,
      would_exceed: false,
    });
    expect(c.market_twin.session_ready).toBe(false);
    expect(c.interrogation).toBeNull();
    expect(c.pack_ready).toBe(false);
    expect(c.purchase_executed).toBe(false);
  });

  it("would_exceed on interrogation blocks pack when market ready", () => {
    const c = composeMarketplaceHtmlTwinInterrogation({
      ...freeMarketBase(),
      include_interrogation: true,
      questions: [questions[0]],
      chase_mode: "single_question",
      models,
      selected_model_id: "gpt-5.5",
      daily_cap_usd: 1,
      spent_usd: 0.9,
      projected_cost_usd_high: 0.5,
      would_exceed: true,
    });
    expect(c.market_twin.session_ready).toBe(true);
    expect(c.interrogation?.loop_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("operator_ack false blocks", () => {
    const c = composeMarketplaceHtmlTwinInterrogation({
      ...freeMarketBase(),
      operator_ack: false,
      include_interrogation: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.store_mutated).toBe(false);
  });
});
