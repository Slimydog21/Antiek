import type { Meta, StoryObj } from "@storybook/react";

import { KeyChip } from "./KeyChip";

const meta: Meta<typeof KeyChip> = {
  title: "Hotkeys/KeyChip",
  component: KeyChip,
};
export default meta;

type Story = StoryObj<typeof KeyChip>;

export const Combo: Story = {
  args: {
    binding: "mod+k",
    label: "Command palette",
  },
};

export const ComboWithShift: Story = {
  args: {
    binding: "mod+shift+p",
    label: "Command palette (alt)",
  },
};

export const Chord: Story = {
  args: {
    binding: "g r",
    label: "Go to Research",
  },
};

export const SingleKey: Story = {
  args: {
    binding: "?",
    label: "Show keyboard shortcuts",
  },
};

export const Medium: Story = {
  args: {
    binding: "g e",
    label: "Go to Read",
    size: "md",
  },
};
