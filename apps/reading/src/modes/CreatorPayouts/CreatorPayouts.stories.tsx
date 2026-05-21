import type { Meta, StoryObj } from "@storybook/react";

import CreatorPayouts from "./index";

/**
 * Creator Payouts — Sprint 23-24 self-service view.
 *
 * Renders the calling user's accrued + paid + rollover history.
 * In Storybook the backend fetch fails silently; the page sits
 * in its loading state with the headline + intro copy visible.
 */
const meta = {
  title: "Creator / CreatorPayouts",
  component: CreatorPayouts,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof CreatorPayouts>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LoadingState: Story = {};
