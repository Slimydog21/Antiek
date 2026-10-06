import type { Meta, StoryObj } from "@storybook/react";

import SkillRules from "./index";

/**
 * SkillRules page — read-only operator surface for the shared
 * substrate's cross-user promoted rules (master-spec §13.2 + §13.9).
 *
 * Stories render the full page. Storybook has no backend, so
 * GET /skill-rules fails and the page renders its failure state: a
 * dash in each confidence tile and "Skill rules didn't load." with
 * Try again (a failed load is never shown as "No promoted rules
 * yet"). Real fetch behavior is covered by
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
 * Default story — with no backend in Storybook this shows the failure
 * state described above. The name stays EmptyState so its lost-pixel
 * baseline path is unchanged.
 */
export const EmptyState: Story = {};
