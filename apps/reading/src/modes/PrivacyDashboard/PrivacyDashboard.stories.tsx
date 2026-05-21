import type { Meta, StoryObj } from "@storybook/react";

import PrivacyDashboard from "./index";

/**
 * Privacy Dashboard — first-class operator-facing surface for the
 * substrate's DP posture (master-spec §13.3).
 *
 * Stories render the full page. The backend fetch (/trust-center +
 * /trust-center/deletion-requests) degrades silently in Storybook,
 * so the page sits in its loading state with no telemetry sections
 * — which is itself a useful snapshot of the chrome + headers +
 * the substrate-wide ε total surface.
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

export const LoadingState: Story = {};
