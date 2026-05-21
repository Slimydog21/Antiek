import type { Meta, StoryObj } from "@storybook/react";

import OutcomesIndex from "./index";

/**
 * Outcomes audit listing — operator-facing cross-investigation
 * grading history (master-spec §13.8).
 *
 * In Storybook (no backend) the listing renders empty with the
 * "grade a synthesis to populate this view" nudge — useful as a
 * visual snapshot of the empty state copy + filter input chrome.
 */
const meta = {
  title: "Trust / OutcomesIndex",
  component: OutcomesIndex,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof OutcomesIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
