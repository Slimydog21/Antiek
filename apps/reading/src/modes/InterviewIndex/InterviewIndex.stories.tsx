import type { Meta, StoryObj } from "@storybook/react";

import InterviewIndex from "./index";

/**
 * Interview index — operator-facing project + invite surface
 * (master-spec §11.5).
 *
 * Storybook renders the page in its empty state — no projects load
 * from the backend. The "new project" form is fully editable; the
 * submit button posts to a missing endpoint and surfaces the
 * error inline. Useful as a chrome regression target.
 */
const meta = {
  title: "Workstation / InterviewIndex",
  component: InterviewIndex,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof InterviewIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
