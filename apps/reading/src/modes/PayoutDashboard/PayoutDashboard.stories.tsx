import type { Meta, StoryObj } from "@storybook/react";

import PayoutDashboard from "./index";

/**
 * Payout Dashboard — Sprint 25+ unified operator view.
 *
 * Renders creator + publisher rev-share lines side-by-side with
 * filter + monthly totals + platform residual. Storybook fetches
 * fail silently; the page sits in its empty-state.
 */
const meta = {
  title: "Operator / PayoutDashboard",
  component: PayoutDashboard,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PayoutDashboard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
