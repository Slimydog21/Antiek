import type { Meta, StoryObj } from "@storybook/react";

import Billing from "./index";

/**
 * Billing summary page — operator-facing usage + margin view
 * (master-spec §13.5).
 *
 * Storybook renders the loading state. Once the backend resolves,
 * the page shows a free-tier progress bar, two margin cards
 * (paid-public 10% / paid-private 50%), and a totals section.
 * User + period are editable; defaults are __operator__ +
 * current YYYY-MM.
 */
const meta = {
  title: "Trust / Billing",
  component: Billing,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Billing>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
