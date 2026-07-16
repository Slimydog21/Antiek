import type { Meta, StoryObj } from "@storybook/react";
import { SkillRuleDetailView, type SkillRuleDetailRecord } from "./index";

const rule: SkillRuleDetailRecord = {
  rule_id: "skill-source-triangulation-81e7",
  rule_text:
    "Triangulate supplier road-map claims against hiring signals, shipment evidence, and customer deployment constraints before assigning a date.",
  rule_kind: "source_tier_rule",
  domain: "Semiconductors",
  epsilon_budget_consumed: 0.0125,
  source_user_count: 8,
  confidence: "moderate",
  extracted_at: "2026-06-14T11:20:00Z",
};
const meta = {
  title: "Trust / Skill Rule Specimen",
  component: SkillRuleDetailView,
  parameters: {
    layout: "fullscreen",
    lostpixel: { waitBeforeScreenshot: 500 },
  },
  tags: ["autodocs", "a11y-audit"],
  args: {
    ruleId: rule.rule_id,
    rule,
    state: "ready",
    onRetry: () => undefined,
  },
} satisfies Meta<typeof SkillRuleDetailView>;
export default meta;
type Story = StoryObj<typeof meta>;
export const PromotedRule: Story = {};
export const Loading: Story = { args: { rule: null, state: "loading" } };
export const NotFound: Story = { args: { rule: null, state: "not-found" } };
export const SafeFailure: Story = { args: { rule: null, state: "error" } };
export const MalformedResponse: Story = {
  args: { rule: {} as SkillRuleDetailRecord },
};
export const UnknownMetadata: Story = {
  args: {
    rule: {
      ...rule,
      source_user_count: Number.NaN,
      epsilon_budget_consumed: -0.01,
      confidence: "",
      extracted_at: "not-a-date",
    },
  },
};
export const LongContent: Story = {
  args: {
    rule: {
      ...rule,
      rule_id: `${rule.rule_id}-${"long".repeat(24)}`,
      rule_text: `${rule.rule_text} ${"Preserve the original uncertainty boundary during every later review. ".repeat(5)}`,
    },
  },
};
export const Narrow: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
export const Night: Story = {
  parameters: { backgrounds: { default: "dark" } },
};
