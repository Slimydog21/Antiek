import { describe, expect, it } from "vitest";
import {
  composeHighlightFloatRecursiveTwinMoCompetition,
  formatHighlightFloatRecursiveTwinMoCompetitionSummary,
} from "./highlightFloatRecursiveTwinMoCompetitionCompose";

const MO_COMP = {
  mo: {
    operator_id: "op-1",
    work_minutes: 120,
    goals: [
      { goal_id: "g1", title: "Survey arxiv competition gaps" },
      { goal_id: "g2", title: "Draft twin notes" },
    ],
    usd_per_hour: 15,
    approved_ceiling_usd: 40,
    unattended_ack: true,
    spend_consent: true,
  },
  research: {
    decision: {
      selected_model_id: "gpt-5.5",
      models: [
        {
          model_id: "gpt-5.5",
          tier: "frontier",
          projected_cost_usd_high: 2,
          projected_cost_usd_low: 1,
        },
      ],
      daily_cap_usd: 50,
      spent_usd: 10,
    },
    competition_view: {
      session_id: "sess-1",
      asset_id: "book-1",
      html_projection_sha: "sha-html-1",
      view_requested: true,
      twin_bound: true,
      twin_substrate_ready: true,
      claimed_format: "html" as const,
      competition: {
        draft_id: "draft-1",
        parent_asset_id: "book-1",
        competitor_decisions: [
          {
            competitor: "Perplexity",
            area: "citation_grounding" as const,
            decision_summary: "Inline citations with source cards",
            antiek_status: "parity" as const,
          },
          {
            competitor: "OpenAI DR",
            area: "multi_agent_orchestration" as const,
            decision_summary: "Planner + browser agents",
            antiek_status: "behind" as const,
            residual: "strengthen collective floating cohesive pack",
          },
        ],
        requested_families: ["arxiv" as const, "substack" as const],
        citations: [
          {
            citation_id: "c1",
            family: "arxiv" as const,
            title: "Scaling Laws under Noise",
            external_id: "arxiv:2301.00001",
          },
          {
            citation_id: "c2",
            family: "substack" as const,
            title: "Research notes on evals",
            url: "https://example.substack.com/p/evals",
          },
        ],
        quality_overall: 0.8,
        quality_floor: 0.5,
        would_exceed: false,
        search_query: "scaling orchestration citations",
      },
    },
  },
};

describe("composeHighlightFloatRecursiveTwinMoCompetition", () => {
  it("highlight float + MO twin competition ready", () => {
    const c = composeHighlightFloatRecursiveTwinMoCompetition({
      highlight_surface: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        highlight: "scaling laws under noise",
        gated: false,
        would_exceed: false,
        surface_action: "spawn_only",
        operator_ack: true,
        source_families: ["arxiv"],
        twin_findings: [
          {
            source_id: "extra-1",
            body: "claim A supported",
            kind: "insight",
          },
        ],
        mark_for_prompt_context: true,
      },
      mo_competition: MO_COMP,
      operator_ack: true,
    });
    expect(c.highlight_surface.pack_ready).toBe(true);
    expect(c.mo_competition.pack_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.live_dispatched).toBe(false);
    expect(c.twin_written).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
    expect(c.authority).toBe(
      "highlight_float_recursive_twin_mo_competition_compose_advisory",
    );
    expect(formatHighlightFloatRecursiveTwinMoCompetitionSummary(c)).toMatch(
      /live_dispatched=false/,
    );
  });

  it("gated highlight throws", () => {
    expect(() =>
      composeHighlightFloatRecursiveTwinMoCompetition({
        highlight_surface: {
          session_id: "s",
          parent_asset_id: "b",
          highlight: "secret",
          gated: true,
          would_exceed: false,
          surface_action: "spawn_only",
          operator_ack: true,
        },
        mo_competition: MO_COMP,
        operator_ack: true,
      }),
    ).toThrow(/gated/);
  });

  it("operator_ack false blocks", () => {
    const c = composeHighlightFloatRecursiveTwinMoCompetition({
      highlight_surface: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        highlight: "scaling laws under noise",
        gated: false,
        would_exceed: false,
        surface_action: "spawn_only",
        operator_ack: false,
      },
      mo_competition: MO_COMP,
      operator_ack: false,
    });
    expect(c.pack_ready).toBe(false);
    expect(c.twin_written).toBe(false);
  });

  it("unattended false blocks mo path", () => {
    const c = composeHighlightFloatRecursiveTwinMoCompetition({
      highlight_surface: {
        session_id: "sess-1",
        parent_asset_id: "book-1",
        highlight: "scaling laws under noise",
        gated: false,
        would_exceed: false,
        surface_action: "spawn_only",
        operator_ack: true,
      },
      mo_competition: {
        ...MO_COMP,
        mo: { ...MO_COMP.mo, unattended_ack: false },
      },
      operator_ack: true,
    });
    expect(c.mo_competition.pack_ready).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.live_execution_authorized).toBe(false);
  });
});
