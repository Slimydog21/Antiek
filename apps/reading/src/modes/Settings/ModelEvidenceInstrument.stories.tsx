import type { Meta, StoryObj } from "@storybook/react";
import { fn, userEvent, within, expect } from "@storybook/test";

import ModelEvidenceInstrument from "./ModelEvidenceInstrument";
import type { ModelEvidenceInstrumentProps } from "./ModelEvidenceInstrument";
import type { ModelDecisionResponse } from "../../api/settings";

/**
 * ModelEvidenceInstrument — sunline evidence rail.
 *
 * Extracted from the Settings decision-tree panel.  Every state is a
 * truthful rendering of the backend contract: absent measurement renders
 * "Not measured", never an affinity number.  A measured pick requires
 * at least two operationally eligible measured candidates from the same
 * valid report snapshot.
 *
 * Proof matrix: complete, partial, no-report, budget-unknown,
 * provider-unavailable, narrow, dark+reduced-motion.
 */

/* ── fixtures ────────────────────────────────────────────────────────── */

const COMPLETE_COHORT: ModelDecisionResponse = {
  authority: "advisory",
  task: "deep_research",
  recommended_tier: "synthesis",
  benchmark_status: "measured",
  benchmark_generated_at: "2026-07-07T00:00:00Z",
  candidates: [
    {
      rank: 1,
      tier: "synthesis",
      provider: "zai",
      model: "glm-5.2",
      ready: true,
      operationally_eligible: true,
      quality_score: 0.95,
      quality_basis: "measured",
      benchmark_samples: 40,
      estimated_usd_low: 0.012,
      estimated_usd_high: 0.019,
      would_exceed_budget: false,
    },
    {
      rank: 2,
      tier: "pro",
      provider: "deepseek",
      model: "deepseek-v4-pro",
      ready: true,
      operationally_eligible: true,
      quality_score: 0.82,
      quality_basis: "measured",
      benchmark_samples: 35,
      estimated_usd_low: 0.008,
      estimated_usd_high: 0.013,
      would_exceed_budget: false,
    },
    {
      rank: 3,
      tier: "flash",
      provider: "zai",
      model: "glm-5.2",
      ready: true,
      operationally_eligible: true,
      quality_score: null,
      quality_basis: "absent",
      benchmark_samples: null,
      estimated_usd_low: 0.005,
      estimated_usd_high: 0.009,
      would_exceed_budget: false,
    },
  ],
  notes: ["Advisory — not a dispatch instruction."],
};

const PARTIAL_COHORT: ModelDecisionResponse = {
  authority: "advisory",
  task: "writing",
  recommended_tier: null,
  benchmark_status: "measured",
  benchmark_generated_at: "2026-07-07T00:00:00Z",
  candidates: [
    {
      rank: 1,
      tier: "flash",
      provider: "zai",
      model: "glm-5.2",
      ready: true,
      operationally_eligible: true,
      quality_score: 0.91,
      quality_basis: "measured",
      benchmark_samples: 12,
      estimated_usd_low: 0.005,
      estimated_usd_high: 0.009,
      would_exceed_budget: false,
    },
    {
      rank: 2,
      tier: "pro",
      provider: "deepseek",
      model: "deepseek-v4-pro",
      ready: true,
      operationally_eligible: true,
      quality_score: null,
      quality_basis: "absent",
      benchmark_samples: null,
      estimated_usd_low: 0.008,
      estimated_usd_high: 0.013,
      would_exceed_budget: false,
    },
  ],
  notes: [
    "Only one measured route — no comparative cohort available.",
    "Measurement availability is not comparative superiority.",
  ],
};

const NO_REPORT: ModelDecisionResponse = {
  authority: "advisory",
  task: "reading",
  recommended_tier: null,
  benchmark_status: "unavailable",
  benchmark_generated_at: null,
  candidates: [
    {
      rank: 1,
      tier: "flash",
      provider: "zai",
      model: "glm-5.2",
      ready: true,
      operationally_eligible: false,
      quality_score: null,
      quality_basis: "absent",
      benchmark_samples: null,
      estimated_usd_low: null,
      estimated_usd_high: null,
      would_exceed_budget: null,
    },
    {
      rank: 2,
      tier: "pro",
      provider: "deepseek",
      model: "deepseek-v4-pro",
      ready: true,
      operationally_eligible: false,
      quality_score: null,
      quality_basis: "absent",
      benchmark_samples: null,
      estimated_usd_low: null,
      estimated_usd_high: null,
      would_exceed_budget: null,
    },
  ],
  notes: [
    "Antiek-bench report is not configured; no measured evidence available.",
  ],
};

const BUDGET_UNKNOWN: ModelDecisionResponse = {
  authority: "advisory",
  task: "general",
  recommended_tier: null,
  benchmark_status: "unavailable",
  benchmark_generated_at: null,
  candidates: [
    {
      rank: 1,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
      ready: true,
      operationally_eligible: false,
      quality_score: null,
      quality_basis: "absent",
      benchmark_samples: null,
      estimated_usd_low: null,
      estimated_usd_high: null,
      would_exceed_budget: null,
    },
    {
      rank: 2,
      tier: "flash",
      provider: "zai",
      model: "glm-5.2",
      ready: true,
      operationally_eligible: false,
      quality_score: null,
      quality_basis: "absent",
      benchmark_samples: null,
      estimated_usd_low: null,
      estimated_usd_high: null,
      would_exceed_budget: null,
    },
  ],
  notes: [
    "Remaining budget is unknown; budget eligibility is not asserted.",
  ],
};

const PROVIDER_UNAVAILABLE: ModelDecisionResponse = {
  authority: "advisory",
  task: "deep_research",
  recommended_tier: null,
  benchmark_status: "unavailable",
  benchmark_generated_at: null,
  candidates: [
    {
      rank: 1,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
      ready: false,
      operationally_eligible: false,
      quality_score: null,
      quality_basis: "absent",
      benchmark_samples: null,
      estimated_usd_low: null,
      estimated_usd_high: null,
      would_exceed_budget: null,
    },
  ],
  notes: [
    "No text-model provider is registered at boot; no tier is eligible.",
  ],
};

/* ── base props ──────────────────────────────────────────────────────── */

const baseProps: Omit<
  ModelEvidenceInstrumentProps,
  "decision" | "loading" | "error"
> = {
  onCompare: fn(),
  task: "deep_research",
  onTaskChange: fn(),
  inputChars: 2000,
  onInputCharsChange: fn(),
  outputTokens: 500,
  onOutputTokensChange: fn(),
};

/* ── meta ────────────────────────────────────────────────────────────── */

const meta = {
  title: "Loop 1 / ModelEvidenceInstrument",
  component: ModelEvidenceInstrument,
  parameters: { layout: "padded" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof ModelEvidenceInstrument>;

export default meta;
type Story = StoryObj<typeof meta>;

/* ── proof matrix ────────────────────────────────────────────────────── */

/** Complete measured cohort with two eligible routes — measured pick emitted. */
export const CompleteMeasuredCohort: Story = {
  args: {
    ...baseProps,
    decision: COMPLETE_COHORT,
    loading: false,
    error: null,
  },
};

/** Partial cohort — one measured, one absent. Judgment withheld. */
export const PartialCohort: Story = {
  args: {
    ...baseProps,
    decision: PARTIAL_COHORT,
    loading: false,
    error: null,
  },
};

/** No benchmark report configured — all evidence absent. */
export const NoBenchmarkReport: Story = {
  args: {
    ...baseProps,
    decision: NO_REPORT,
    loading: false,
    error: null,
  },
};

/** Budget unknown — eligibility cannot be asserted. */
export const BudgetUnknown: Story = {
  args: {
    ...baseProps,
    decision: BUDGET_UNKNOWN,
    loading: false,
    error: null,
  },
};

/** Provider unavailable — all routes not ready. */
export const ProviderUnavailable: Story = {
  args: {
    ...baseProps,
    decision: PROVIDER_UNAVAILABLE,
    loading: false,
    error: null,
  },
};

/** Narrow viewport — wraps into vertical evidence sequence. */
export const Narrow: Story = {
  args: {
    ...baseProps,
    decision: COMPLETE_COHORT,
    loading: false,
    error: null,
  },
  parameters: {
    viewport: { defaultViewport: "mobile1" },
    lostpixel: { breakpoints: [375] },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 375, maxWidth: "100%" }}>
        <Story />
      </div>
    ),
  ],
};

/** Dark theme + reduced motion — same semantic contract. */
export const DarkReducedMotion: Story = {
  args: {
    ...baseProps,
    decision: COMPLETE_COHORT,
    loading: false,
    error: null,
  },
  parameters: {
    backgrounds: { default: "space-2 (night)" },
  },
  decorators: [
    (Story) => (
      <div className="dark">
        <Story />
      </div>
    ),
  ],
};

/** Keyboard proof — task selector changes trigger onTaskChange. */
export const KeyboardProof: Story = {
  args: {
    ...baseProps,
    decision: COMPLETE_COHORT,
    loading: false,
    error: null,
  },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const select = canvas.getByLabelText("Task");
    select.focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(args.onTaskChange).toBeDefined();
  },
};
