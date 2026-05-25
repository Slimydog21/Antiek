import type { Meta, StoryObj } from "@storybook/react";

import ProjectTree from "./ProjectTree";

/**
 * ProjectTree — the dockable nav panel with Pinned / Recent / All
 * sections. Click a row to navigate; Cmd-click to open as a floating
 * panel; click the ☆/★ to pin.
 */
const meta = {
  title: "Navigation / ProjectTree",
  component: ProjectTree,
  parameters: { layout: "padded" },
  // `a11y-audit` opts this story into the test-runner axe gate.
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof ProjectTree>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="w-[320px] h-[640px] bg-ice-1 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z2 dark:shadow-z2-night overflow-y-auto">
      <ProjectTree />
    </div>
  ),
};
