import type { Meta, StoryObj } from "@storybook/react";

import PrivacyDashboard from "./index";

/**
 * Privacy Dashboard — first-class surface for privacy controls.
 *
 * Stories render the full page. Without a backend, the page shows
 * its header plus a friendly load error.
 */
const meta = {
  title: "Trust / PrivacyDashboard",
  component: PrivacyDashboard,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PrivacyDashboard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const BackendUnavailable: Story = {};
