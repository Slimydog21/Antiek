import type { Meta, StoryObj } from "@storybook/react";

import LemonButton from "./LemonButton";

const meta = {
  title: "Lemon / Button",
  component: LemonButton,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof LemonButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Grid: Story = {
  render: () => (
    <div className="grid grid-cols-4 gap-4 p-6 items-end">
      {(["primary", "secondary", "tertiary", "danger"] as const).flatMap((v) =>
        (["sm", "md", "lg"] as const).map((s) => (
          <LemonButton key={`${v}-${s}`} variant={v} size={s}>
            {v} · {s}
          </LemonButton>
        )),
      )}
    </div>
  ),
};

export const Disabled: Story = {
  render: () => (
    <div className="flex gap-3 p-6">
      <LemonButton variant="primary" disabled>Disabled primary</LemonButton>
      <LemonButton variant="secondary" disabled>Disabled secondary</LemonButton>
      <LemonButton variant="danger" disabled>Disabled danger</LemonButton>
    </div>
  ),
};

export const WithIcons: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3 p-6">
      <LemonButton icon={<span>↑</span>}>Upload</LemonButton>
      <LemonButton variant="primary" iconRight={<span>↵</span>}>Submit</LemonButton>
      <LemonButton variant="tertiary" icon={<span>⋯</span>}>More</LemonButton>
      <LemonButton variant="danger" icon={<span>⌫</span>}>Delete</LemonButton>
    </div>
  ),
};

export const FullWidth: Story = {
  render: () => (
    <div className="p-6 max-w-md">
      <LemonButton variant="primary" fullWidth size="lg">
        Begin investigation
      </LemonButton>
    </div>
  ),
};
