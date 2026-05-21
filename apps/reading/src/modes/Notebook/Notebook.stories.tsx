import type { Meta, StoryObj } from "@storybook/react";

import Notebook from "./index";

/**
 * S7-light story — renders the legacy Notebook surface inside a panel
 * frame so the operator can preview it as a workspace panel.
 *
 * The full TipTap-based S7 (block editor + 9 block kinds + slash menu +
 * autosave) is deferred until the SPR-08/09/11 notebook-track merge
 * lands on main. See `apps/reading/S7-FOLLOWUP.md`.
 */
const meta = {
  title: "Loop 1 / Notebook",
  component: Notebook,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof Notebook>;

export default meta;
type Story = StoryObj<typeof meta>;

export const InPanelFrame: Story = {
  render: () => (
    <div className="p-6 bg-ice-2 dark:bg-space-2 h-screen flex items-center justify-center">
      <div className="w-[720px] h-[560px] bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night overflow-hidden">
        <Notebook />
      </div>
    </div>
  ),
};

export const FullSlot: Story = {
  render: () => (
    <div className="h-screen bg-ice-2 dark:bg-space-2">
      <Notebook />
    </div>
  ),
};
