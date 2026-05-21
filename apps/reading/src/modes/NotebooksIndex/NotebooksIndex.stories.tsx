import type { Meta, StoryObj } from "@storybook/react";

import NotebooksIndex from "./index";

/**
 * Notebooks listing — Wedge 2 linchpin (master-spec §4.2).
 *
 * Storybook empty state: filter chips visible, "new notebook"
 * form editable, listing empty. The page is useful as a visual
 * regression target for the form + filter chrome.
 */
const meta = {
  title: "PostHog Wedges / NotebooksIndex",
  component: NotebooksIndex,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof NotebooksIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
