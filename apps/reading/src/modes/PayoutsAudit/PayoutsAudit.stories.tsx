import type { Meta, StoryObj } from "@storybook/react";

import PayoutsAudit from "./index";

/**
 * Payouts audit page — operator-facing Stripe Connect transfer log
 * (master-spec §13.7 + §9.10).
 *
 * Storybook has no backend, so the transfers request fails and the
 * page renders its failure state: the filter chips + recipient input,
 * a dash in every status tile (the totals are unknown, not zero) and
 * "Transfers didn't load." with Try again. The story keeps its
 * EmptyState name so its lost-pixel baseline path is unchanged.
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
