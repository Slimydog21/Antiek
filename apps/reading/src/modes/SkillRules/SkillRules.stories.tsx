import type { Meta, StoryObj } from "@storybook/react";

import SkillRules from "./index";

/**
 * SkillRules page — read-only operator surface for the shared
 * substrate's cross-user promoted rules (master-spec §13.2 + §13.9).
 *
 * Stories render the full page. The backend fetch
 * (GET /skill-rules) fails silently in Storybook (no server) so
 * the page renders the empty state, which is itself a useful
 * snapshot ("No promoted rules yet" with the §13.9 promotion
 * threshold explainer). Real fetch behavior is covered by
 * test_api_skill_rules_listing.py.
 */
const meta = {
  title: "PostHog Wedges / SkillRules",
  component: SkillRules,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof SkillRules>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Default story — page renders in its empty-state because Storybook
 * has no backend. The page is intentionally informative even when
 * empty: the §13.9 promotion threshold explainer is on-screen so
 * the operator understands why no rules are listed yet.
 */
export const EmptyState: Story = {};
