import type { Meta, StoryObj } from "@storybook/react";

import AdvertiserConsole from "./index";

/**
 * Advertiser Console — Sprint 23-24 operator-only campaign management.
 *
 * Lead-gen inventory + sector/intent targeting + per-campaign
 * performance reporting. In Storybook the backend fetch fails
 * silently; the page sits in its empty-state with the headline
 * + intro copy + filter chips visible.
 */
const meta = {
  title: "Operator / AdvertiserConsole",
  component: AdvertiserConsole,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof AdvertiserConsole>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
