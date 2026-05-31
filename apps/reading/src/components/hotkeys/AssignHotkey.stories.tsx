import type { Meta, StoryObj } from "@storybook/react";

import { AssignHotkey } from "./AssignHotkey";

const meta: Meta<typeof AssignHotkey> = {
  title: "Hotkeys/AssignHotkey",
  component: AssignHotkey,
};
export default meta;

type Story = StoryObj<typeof AssignHotkey>;

export const Unassigned: Story = {
  args: {
    entityId: "inv-demo-1",
    route: "/inv/inv-demo-1",
    entityKind: "investigation",
    label: "Why did the Roman aqueducts fail?",
  },
};
