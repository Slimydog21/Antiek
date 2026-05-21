import type { Meta, StoryObj } from "@storybook/react";

import TrustCenter from "./index";

/**
 * Trust Center — public-facing transparency surface (master-spec §13.7).
 *
 * Renders ε budgets, substrate controls, compliance frameworks, and
 * Loop 3 unlock status. In Storybook the backend fetch fails
 * silently; the page sits in its loading state with the static
 * intro copy + headline visible.
 */
const meta = {
  title: "Trust / TrustCenter",
  component: TrustCenter,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof TrustCenter>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LoadingState: Story = {};
