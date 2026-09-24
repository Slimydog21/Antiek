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

// Never quietly disabled: each carries the reason, shown as a tip on hover
// and on keyboard focus (Tab to one) and read out as its description.
export const Disabled: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3 p-6 pt-14">
      <LemonButton variant="primary" disabledReason="Type a question first">Ask</LemonButton>
      <LemonButton variant="secondary" disabledReason="Nothing to export yet">Export HTML</LemonButton>
      <LemonButton variant="danger" disabledReason="Another action is still running">Delete</LemonButton>
      <LemonButton variant="tertiary" disabledReason="You are on the first page">Previous</LemonButton>
    </div>
  ),
};

// The reason tip as it shows when the button holds keyboard focus.
export const DisabledReasonFocused: Story = {
  render: () => (
    <div className="p-6 pt-14">
      <LemonButton variant="primary" disabledReason="Connect a model in Settings first" autoFocus>
        Start research
      </LemonButton>
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
