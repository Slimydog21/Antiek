import type { Meta, StoryObj } from "@storybook/react";

import { HotkeyHud } from "./HotkeyHud";

const meta: Meta<typeof HotkeyHud> = {
  title: "Hotkeys/HotkeyHud",
  component: HotkeyHud,
};
export default meta;

type Story = StoryObj<typeof HotkeyHud>;

/** Controlled open so the audit/Storybook renders the overlay content. */
export const Open: Story = {
  args: {
    open: true,
    onClose: () => {},
  },
};
