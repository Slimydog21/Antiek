import type { Meta, StoryObj } from "@storybook/react";

import LemonTag from "./LemonTag";

const meta = {
  title: "Lemon / Tag",
  component: LemonTag,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof LemonTag>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AllColours: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2 p-6">
      <LemonTag>default</LemonTag>
      <LemonTag colour="sun">sun</LemonTag>
      <LemonTag colour="aurora">aurora</LemonTag>
      <LemonTag colour="danger">danger</LemonTag>
      <LemonTag colour="muted">muted</LemonTag>
    </div>
  ),
};

export const WithDot: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2 p-6">
      <LemonTag dot>running</LemonTag>
      <LemonTag dot colour="sun">flagged</LemonTag>
      <LemonTag dot colour="danger">failed</LemonTag>
    </div>
  ),
};

export const Removable: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2 p-6">
      <LemonTag onRemove={() => alert("removed")}>kalshi</LemonTag>
      <LemonTag colour="sun" onRemove={() => alert("removed")}>research</LemonTag>
      <LemonTag colour="aurora" onRemove={() => alert("removed")}>NVDA Q4</LemonTag>
    </div>
  ),
};
