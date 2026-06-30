import type { Meta, StoryObj } from "@storybook/react";

import Federation from "./index";

/**
 * Federation config page — operator surface for the substrate-wide
 * cross-graph federation policy (master-spec §13.9 Phase 3).
 *
 * In Storybook (no backend) the page surfaces the same inline network
 * error path operators see if /federation/config is unavailable.
 */
const meta = {
  title: "Trust / Federation",
  component: Federation,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Federation>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
