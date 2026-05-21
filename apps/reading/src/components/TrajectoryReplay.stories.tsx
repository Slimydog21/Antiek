import type { Meta, StoryObj } from "@storybook/react";

import { mockEventStream } from "./__fixtures__";
import TrajectoryReplay from "./TrajectoryReplay";

/**
 * TrajectoryReplay — animated playback of a saved trajectory at a chosen
 * speed multiplier (events replay with synthetic emitted_at offsets).
 * Useful for trajectory-aware UI development and operator review.
 */
const meta = {
  title: "Loop 1 / TrajectoryReplay",
  component: TrajectoryReplay,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof TrajectoryReplay>;

export default meta;
type Story = StoryObj<typeof meta>;

export const TwoX: Story = {
  args: {
    events: mockEventStream,
    playSpeed: 2,
  },
};

export const FourX: Story = {
  args: {
    events: mockEventStream,
    playSpeed: 4,
  },
};

export const Empty: Story = {
  args: {
    events: [],
    playSpeed: 1,
  },
};
