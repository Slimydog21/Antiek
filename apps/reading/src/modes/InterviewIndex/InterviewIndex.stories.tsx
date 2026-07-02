import type { Meta, StoryObj } from "@storybook/react";

import InterviewIndex from "./index";

/**
 * Interview index — operator-facing project + invite surface
 * (master-spec §11.5).
 *
 * Storybook renders the retired standalone index as a chrome regression
 * target. In production, interview acquisition is folded into the one
 * Speak door at /speak; the underlying project + invite endpoints still
 * exist for the Speak console flow.
 */
const meta = {
  title: "Speak / InterviewIndex",
  component: InterviewIndex,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof InterviewIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
