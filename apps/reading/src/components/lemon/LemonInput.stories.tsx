import type { Meta, StoryObj } from "@storybook/react";

import LemonInput from "./LemonInput";

const meta = {
  title: "Lemon / Input",
  component: LemonInput,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof LemonInput>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basic: Story = {
  render: () => (
    <div className="p-6 max-w-md space-y-4">
      <LemonInput placeholder="Plain input…" />
      <LemonInput placeholder="With left icon" iconLeft={<span>⌕</span>} />
      <LemonInput placeholder="Search · ⌘K" iconLeft={<span>⌕</span>} kbdHint="⌘K" />
    </div>
  ),
};

export const Sizes: Story = {
  render: () => (
    <div className="p-6 max-w-md space-y-3">
      <LemonInput sizing="sm" placeholder="sm" />
      <LemonInput sizing="md" placeholder="md (default)" />
      <LemonInput sizing="lg" placeholder="lg" />
    </div>
  ),
};

export const Disabled: Story = {
  render: () => (
    <div className="p-6 max-w-md">
      <LemonInput placeholder="Cannot edit" disabled defaultValue="locked" />
    </div>
  ),
};
