import type { Meta, StoryObj } from "@storybook/react";
import { BacktestView, type BacktestReport } from "./index";

const stable: BacktestReport = {
  synthesis_id: "syn-polar-grid-2042",
  synthesis_timestamp: "2026-03-12T18:30:00Z",
  target_question:
    "Should the research program commit to the polar-grid interoperability standard?",
  status: "conditional",
  implicit_recommendation:
    "Proceed if the interoperability pilot clears its reliability threshold.",
  substrate_manifest_counts: { chunks: 38, edges: 22, documents: 9 },
  added_edges_since: 128,
  superseded_edges_since: 14,
  cited_edges_now_superseded_count: 0,
  chunks_retired_downward_count: 0,
  outcomes_recorded: 0,
  cited_edges_now_superseded: [],
  chunks_retired_downward: [],
  outcomes: [],
};
const weathered: BacktestReport = {
  ...stable,
  cited_edges_now_superseded_count: 1,
  chunks_retired_downward_count: 1,
  outcomes_recorded: 1,
  cited_edges_now_superseded: [
    {
      edge_id: "edge-7b9f-long-identifier",
      source: "Northstar protocol",
      relation: "depends on",
      target: "PolarLink gateway compatibility",
      valid_until: "2026-06-03T10:10:00Z",
      superseded_by: "edge-92d",
    },
  ],
  chunks_retired_downward: [
    {
      chunk_id: "chunk-field-trial-2026-001",
      original_tier: 1,
      override_tier: 3,
      reason: "The field trial did not reproduce under sustained packet loss.",
      set_at: "2026-06-08T12:00:00Z",
    },
  ],
  outcomes: [
    {
      outcome_id: "outcome-1",
      observer: "Research review council",
      observed_at: "2026-07-01T09:00:00Z",
      thesis_outcomes: [
        {
          thesis_claim:
            "The gateway will remain interoperable under degraded links.",
          outcome: "partially_confirmed",
          evidence:
            "Routine traffic held; recovery latency exceeded the archived assumption.",
        },
      ],
      falsification_outcomes: [
        {
          condition: "Recovery exceeds five minutes",
          occurred: true,
          evidence: "Two polar-night trials exceeded seven minutes.",
        },
      ],
      execution_risk_outcomes: [
        {
          risk: "Vendor-specific recovery behavior",
          manifested: true,
          severity_actual: "moderate",
          evidence: "One gateway required a manual reset.",
        },
      ],
      notes:
        "Re-open the reliability assumption before the next procurement gate.",
    },
  ],
};

const meta = {
  title: "Trust / Decision Weather Station",
  component: BacktestView,
  parameters: {
    layout: "fullscreen",
    lostpixel: { waitBeforeScreenshot: 500 },
  },
  tags: ["autodocs", "a11y-audit"],
  args: {
    synthesisId: stable.synthesis_id,
    report: stable,
    state: "ready",
    onRetry: () => undefined,
  },
} satisfies Meta<typeof BacktestView>;
export default meta;
type Story = StoryObj<typeof meta>;
export const QuietWeather: Story = {};
export const CitedEvidenceDrift: Story = { args: { report: weathered } };
export const HumanOutcomesWithoutCitedDrift: Story = {
  args: {
    report: {
      ...weathered,
      cited_edges_now_superseded_count: 0,
      chunks_retired_downward_count: 0,
      cited_edges_now_superseded: [],
      chunks_retired_downward: [],
    },
  },
};
export const SummaryDetailMismatch: Story = {
  args: { report: { ...weathered, cited_edges_now_superseded_count: 4 } },
};
export const MalformedDetailFallback: Story = {
  args: {
    report: {
      ...weathered,
      cited_edges_now_superseded: [{ edge_id: "only-an-id" }],
      outcomes: [{ observer: "Incomplete record" }],
    },
  },
};
export const Loading: Story = { args: { report: null, state: "loading" } };
export const NotArchived: Story = {
  args: { report: null, state: "not-found" },
};
export const SafeFailure: Story = { args: { report: null, state: "error" } };
export const Narrow: Story = {
  args: { report: weathered },
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
export const Night: Story = {
  args: { report: weathered },
  parameters: { backgrounds: { default: "dark" } },
};
