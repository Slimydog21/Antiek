import type { Meta, StoryObj } from "@storybook/react";
import { expect, fn, userEvent, within } from "@storybook/test";
import { useState } from "react";

import ResearchRouteInstrument from "./ResearchRouteInstrument";
import type { ResearchRouteInstrumentProps } from "./ResearchRouteInstrument";
import type { ResearchRoutePreview } from "../../lib/api";

/**
 * ResearchRouteInstrument — the route-choice and budget-readout
 * instrument extracted from StartResearch.
 *
 * The selected lens receives a left-edge sun registration mark; readiness
 * is an instrument status, not a decorative badge. Budget sits below as
 * calibration evidence.
 *
 * Proof matrix: four budget authority cells + unavailable route.
 * Narrow + dark variants exercise the same semantic contract.
 */

/* ── fixtures ────────────────────────────────────────────────────────── */

const TWO_READY_CANDIDATES: ResearchRoutePreview["candidates"] = [
  {
    choice_id: "rr_fast",
    tier: "fast",
    configuration_fingerprint: "cfg-fast",
    display_name: "Fast lens",
    model_policy_label: "GLM-5.2 · thinking off",
    rationale: "Lighter upstream investigation work.",
    ready: true,
    readiness_label: "Ready",
  },
  {
    choice_id: "rr_deep",
    tier: "deep",
    configuration_fingerprint: "cfg-deep",
    display_name: "Deep lens",
    model_policy_label: "GLM-5.2 · thinking on",
    rationale: "More reasoning for upstream investigation work.",
    ready: true,
    readiness_label: "Ready",
  },
];

const ALL_DISABLED_CANDIDATES: ResearchRoutePreview["candidates"] = [
  {
    choice_id: "rr_deep",
    tier: "deep",
    configuration_fingerprint: "cfg-deep",
    display_name: "Deep lens",
    model_policy_label: "GLM-5.2 · thinking on",
    rationale: "Reasoning-heavy work.",
    ready: false,
    readiness_label: "Provider unavailable",
  },
];

const BASE_PROJECTION_NOTE =
  "Trajectory cost is unavailable until measured telemetry supports an estimator.";

const preview = (
  candidates: ResearchRoutePreview["candidates"],
  budget: Partial<ResearchRoutePreview["budget"]> = {},
): ResearchRoutePreview => ({
  policy_version: "research-route.v1",
  prompt_fingerprint: "prompt-proof",
  candidates,
  budget: {
    authority: "advisory",
    daily_cap_usd: null,
    spent_usd: null,
    spent_status: "unknown",
    cap_source: null,
    notes: [],
    projection_status: "unavailable",
    projection_note: BASE_PROJECTION_NOTE,
    ...budget,
  },
});

/* ── meta ────────────────────────────────────────────────────────────── */

const meta = {
  title: "Loop 1 / ResearchRouteInstrument",
  component: ResearchRouteInstrument,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ResearchRouteInstrument>;

export default meta;
type Story = StoryObj<typeof meta>;

function KeyboardProofHarness(args: ResearchRouteInstrumentProps) {
  const [selectedChoiceId, setSelectedChoiceId] = useState(
    args.selectedChoiceId,
  );
  return (
    <ResearchRouteInstrument
      {...args}
      selectedChoiceId={selectedChoiceId}
      onSelect={(candidate) => {
        args.onSelect(candidate);
        setSelectedChoiceId(candidate.choice_id);
      }}
    />
  );
}

/* ── proof matrix: four budget cells ─────────────────────────────────── */

/** Configured + known: exact spend, operator ceiling, active meter. */
export const ConfiguredKnown: Story = {
  args: {
    preview: preview(TWO_READY_CANDIDATES, {
      daily_cap_usd: 8,
      spent_usd: 2,
      spent_status: "known",
      cap_source: "ANTIEK_OPERATOR_BUDGET_USD",
    }),
    selectedChoiceId: "rr_deep",
    busy: false,
    onSelect: fn(),
  },
};

/** Configured + unknown: unknown spend retained beside exact operator ceiling. */
export const ConfiguredUnknown: Story = {
  args: {
    preview: preview(TWO_READY_CANDIDATES, {
      daily_cap_usd: 8,
      spent_usd: null,
      spent_status: "unknown",
      cap_source: "ANTIEK_OPERATOR_BUDGET_USD",
    }),
    selectedChoiceId: "rr_deep",
    busy: false,
    onSelect: fn(),
  },
};

/** Unconfigured + known: daemon-tracked spend, no operator ceiling. */
export const UnconfiguredKnown: Story = {
  args: {
    preview: preview(TWO_READY_CANDIDATES, {
      daily_cap_usd: null,
      spent_usd: 2,
      spent_status: "known",
      cap_source: null,
      notes: ["No operator cap is configured; the daemon default is reference-only."],
    }),
    selectedChoiceId: "rr_fast",
    busy: false,
    onSelect: fn(),
  },
};

/** Unconfigured + unknown: neither value invented; reference note preserved. */
export const UnconfiguredUnknown: Story = {
  args: {
    preview: preview(TWO_READY_CANDIDATES, {
      daily_cap_usd: null,
      spent_usd: null,
      spent_status: "unknown",
      cap_source: null,
      notes: ["No operator cap is configured; the daemon default is reference-only."],
    }),
    selectedChoiceId: "rr_fast",
    busy: false,
    onSelect: fn(),
  },
};

/* ── unavailable route ───────────────────────────────────────────────── */

/** All routes unavailable: disabled route, recovery copy, no false readiness. */
export const UnavailableRoute: Story = {
  args: {
    preview: preview(ALL_DISABLED_CANDIDATES, {
      daily_cap_usd: null,
      spent_usd: null,
      spent_status: "unknown",
      cap_source: null,
    }),
    selectedChoiceId: "rr_deep",
    busy: false,
    onSelect: fn(),
  },
};

/* ── visual variants ─────────────────────────────────────────────────── */

/** Narrow viewport: the same semantic contract at 375px. */
export const Narrow: Story = {
  args: { ...ConfiguredKnown.args },
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

/** Dark surface: instrument on a night-themed background. */
export const Dark: Story = {
  args: { ...ConfiguredKnown.args },
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

/** Keyboard proof: the production component moves focus and reports selection. */
export const KeyboardProof: Story = {
  args: { ...ConfiguredKnown.args, selectedChoiceId: "rr_fast", onSelect: fn() },
  render: (args) => <KeyboardProofHarness {...args} />,
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const fast = canvas.getByRole("radio", { name: /Fast lens/i });
    const deep = canvas.getByRole("radio", { name: /Deep lens/i });
    fast.focus();
    await userEvent.keyboard("{ArrowRight}");
    await expect(args.onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ choice_id: "rr_deep" }),
    );
    await expect(deep).toHaveFocus();
    await expect(deep).toHaveAttribute("aria-checked", "true");
  },
};
