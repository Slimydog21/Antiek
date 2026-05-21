import type { Meta, StoryObj } from "@storybook/react";

import MarketplaceMetrics from "./index";

/**
 * Marketplace Metrics — Sprint 25+ §2 operator dashboard.
 *
 * Renders creator / publisher / advertiser loops + the derived
 * MarketplaceHealth verdict. In Storybook the backend fetch fails
 * silently; the page sits in its loading state with the static
 * intro copy + headline visible.
 */
const meta = {
  title: "Operator / MarketplaceMetrics",
  component: MarketplaceMetrics,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof MarketplaceMetrics>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LoadingState: Story = {};
