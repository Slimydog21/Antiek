import type { Meta, StoryObj } from "@storybook/react";

import ChatInputArea from "./ChatInputArea";

/**
 * ChatInputArea — the pinned-bottom composer in the ResearchWorkstation.
 * Submit posts an investigation.start_requested event and (by default)
 * navigates to /inv/<new id>. In Storybook the submit handler is wired
 * to `onSubmitted` to capture the action instead of doing real navigation.
 */
const meta = {
  title: "Loop 1 / ChatInputArea",
  component: ChatInputArea,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ChatInputArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: {
    placeholder: "What do you want to research?",
    autoFocus: true,
    onSubmitted: (id) => alert(`submitted, new id = ${id}`),
  },
};

export const ChildOfInvestigation: Story = {
  args: {
    parentInvestigationId: "inv-storybook-demo",
    spawnContext:
      "the gap between groups is a genuine difference in platform physics",
    placeholder: "Ask a follow-up…",
    onSubmitted: (id) => alert(`submitted, new id = ${id}`),
  },
};
