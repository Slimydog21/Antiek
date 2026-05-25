import type { Meta, StoryObj } from "@storybook/react";

import ProjectTree from "./ProjectTree";

/**
 * ProjectTree (SPR-04) — the workflow-scoped content-first tree (zone 2)
 * with Pinned / Recent / All sections. Click a row to navigate; Cmd-click to
 * open as a floating panel; click the ☆/★ to pin.
 *
 * The component reads the active workflow from the route (via
 * `workflowForPath`); the global Storybook preview wraps it in a MemoryRouter
 * so it defaults to Research. The `workflow` prop overrides for a fixed scope.
 *
 * Harvested from PR #8 (caffen/SPR-08) and re-pointed from the deleted
 * `components/navigation/ProjectTree` to the unified `src/shell/ProjectTree`.
 */
const meta = {
  title: "Shell / ProjectTree",
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

export const ReadScope: Story = {
  render: () => (
    <div className="w-[320px] h-[640px] bg-ice-1 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z2 dark:shadow-z2-night overflow-y-auto">
      <ProjectTree workflow="read" />
    </div>
  ),
};
