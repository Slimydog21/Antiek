// SPR-06 / M6 — Storybook: Library / Empty
//
// The empty-state onboarding for the universal library.

import type { Meta, StoryObj } from "@storybook/react";

import { EmptyState } from "./EmptyState";

const meta = {
  title: "Library / Empty",
  component: EmptyState,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {},
};

export const WithCustomSuggestions: Story = {
  args: {
    suggestions: [
      {
        label: "Custom — local fixture A",
        url: "https://example.com/fixture-a",
        kind: "essay",
      },
      {
        label: "Custom — local fixture B",
        url: "https://example.com/fixture-b",
        kind: "article",
      },
      {
        label: "Custom — arXiv fixture",
        url: "https://arxiv.org/abs/0000.00000",
        kind: "paper",
      },
    ],
  },
};
