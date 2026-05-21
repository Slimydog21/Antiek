import type { Meta, StoryObj } from "@storybook/react";

import {
  mockInvestigationCompleted,
  mockInvestigationInProgress,
  mockInvestigationLoading,
} from "../../components/__fixtures__";
import TrajectoryView from "./TrajectoryView";

/**
 * TrajectoryView renders the recursive note-taking + dispatch event
 * stream for an investigation. Stories cover the loading, in-progress,
 * and completed states using fixture data — no network.
 */
const meta = {
  title: "Loop 1 / TrajectoryView",
  component: TrajectoryView,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof TrajectoryView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Loading: Story = {
  args: { investigation: mockInvestigationLoading },
};

export const InProgress: Story = {
  args: { investigation: mockInvestigationInProgress },
};

export const Completed: Story = {
  args: { investigation: mockInvestigationCompleted },
};
