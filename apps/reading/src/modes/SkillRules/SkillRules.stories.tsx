import type { Meta, StoryObj } from "@storybook/react";
import { SkillRulesView, type SkillRule } from "./index";

const rules: SkillRule[] = [
  {
    rule_id: "skill-source-triangulation-81e7",
    rule_text:
      "Triangulate supplier road-map claims against hiring signals, shipment evidence, and customer deployment constraints before assigning a date.",
    rule_kind: "source_tier_rule",
    domain: "Semiconductors",
    epsilon_budget_consumed: 0.0125,
    source_user_count: 8,
    confidence: "high",
    extracted_at: "2026-06-14T11:20:00Z",
  },
  {
    rule_id: "skill-forecast-range-9b21",
    rule_text:
      "Preserve the original forecast range when later evidence narrows the central estimate; do not rewrite uncertainty out of the record.",
    rule_kind: "forecast_discipline",
    domain: "Technology forecasting",
    epsilon_budget_consumed: 0.0075,
    source_user_count: 5,
    confidence: "moderate",
    extracted_at: "2026-06-28T08:45:00Z",
  },
  {
    rule_id:
      "skill-long-identifier-that-must-wrap-without-hiding-provenance-0000000000001",
    rule_text:
      "Separate demonstrated capability from announced capability when comparing research systems across vendors with very long institutional names.",
    rule_kind: "comparison_rule",
    domain: "AI research systems",
    epsilon_budget_consumed: 0.004,
    source_user_count: 3,
    confidence: "low",
    extracted_at: null,
  },
];
const filters = { query: "", domain: "", confidence: "" };
const meta = {
  title: "Trust / Skill Rule Conservatory",
  component: SkillRulesView,
  parameters: {
    layout: "fullscreen",
    lostpixel: { waitBeforeScreenshot: 500 },
  },
  tags: ["autodocs", "a11y-audit"],
  args: {
    rules,
    state: "ready",
    filters,
    onFiltersChange: () => undefined,
    onApply: () => undefined,
    onClear: () => undefined,
    onRetry: () => undefined,
  },
} satisfies Meta<typeof SkillRulesView>;
export default meta;
type Story = StoryObj<typeof meta>;
export const PromotedPractices: Story = {};
export const EmptyBeforePromotion: Story = { args: { rules: [] } };
export const FilteredNoMatches: Story = {
  args: {
    rules: [],
    filters: { query: "packet loss", domain: "Networks", confidence: "high" },
    filtersApplied: true,
  },
};
export const Loading: Story = { args: { rules: [], state: "loading" } };
export const SafeFailure: Story = { args: { rules: [], state: "error" } };
export const UnknownMetadata: Story = {
  args: {
    rules: [
      {
        ...rules[0],
        source_user_count: Number.NaN,
        epsilon_budget_consumed: Number.NaN,
        confidence: "experimental",
        extracted_at: "not-a-date",
      },
    ],
  },
};
export const Narrow: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
export const Night: Story = {
  parameters: { backgrounds: { default: "dark" } },
};
