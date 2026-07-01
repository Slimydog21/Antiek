import type { Meta, StoryObj } from "@storybook/react";

import TrustCenter from "./index";

/**
 * Trust Center — public-facing transparency surface.
 *
 * In Storybook, the backend fetch usually fails and the page shows
 * the header plus its friendly load error instead of live sections.
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

export const BackendUnavailable: Story = {};
