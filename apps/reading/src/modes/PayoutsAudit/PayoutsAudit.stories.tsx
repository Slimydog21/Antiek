import type { Meta, StoryObj } from "@storybook/react";

import PayoutsAudit from "./index";

/**
 * Payouts audit page — operator-facing Stripe Connect transfer log
 * (master-spec §13.7 + §9.10).
 *
 * Stories render the page in its empty-listing state. The status
 * filter chips + recipient input + per-status totals grid are all
 * visible without backend; the totals show zeros across every
 * status bucket.
 */
const meta = {
  title: "Trust / PayoutsAudit",
  component: PayoutsAudit,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PayoutsAudit>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
