import type { Meta, StoryObj } from "@storybook/react";

import NavRail from "./NavRail";

/**
 * NavRail — the always-visible icon column on the far left of AppShell.
 * Renders the Werner mark, mode entries, and footer entries.
 */
const meta = {
  title: "Navigation / NavRail",
  component: NavRail,
  parameters: { layout: "fullscreen" },
  // `a11y-audit` opts this story into the test-runner axe gate
  // (.storybook/test-runner.ts, selected via `--includeTags a11y-audit`).
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof NavRail>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="h-screen flex bg-ice-2 dark:bg-space-2">
      <NavRail />
      <div className="flex-1 flex items-center justify-center text-ink-soft dark:text-moonlight text-sm">
        The active route highlights in yellow + ink left-bar.
      </div>
    </div>
  ),
};
