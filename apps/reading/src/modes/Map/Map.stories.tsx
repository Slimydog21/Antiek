import type { Meta, StoryObj } from "@storybook/react";

import Map from "./index";

/**
 * Application map page — operator's tour of every surface.
 *
 * Renders the canonical route index with keyboard hints for the
 * palette and sidecar. All 21 routes link out to their respective
 * pages.
 */
const meta = {
  title: "Workstation / Map",
  component: Map,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Map>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
