import type { Meta, StoryObj } from "@storybook/react";

import DocumentsIndex from "./index";

/**
 * Documents listing page — substrate-attached sources with per-tier
 * filter chips and a 5-cell per-tier counter grid (master-spec §4.1
 * + §9.5).
 *
 * Empty-state render: the tier counters all show 0, the filter
 * chips are interactive, the empty-list copy explains the filter
 * scope. Useful as a visual regression target for the page chrome.
 */
const meta = {
  title: "Workstation / DocumentsIndex",
  component: DocumentsIndex,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof DocumentsIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
