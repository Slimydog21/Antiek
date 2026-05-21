import type { Meta, StoryObj } from "@storybook/react";

import HeaderBar from "./HeaderBar";

/**
 * HeaderBar — the current top-bar. DEPRECATED in S4 of the UI redesign
 * (superseded by AppShell + NavRail + Topbar), but kept here as the
 * before-state and as cheap insurance during the migration window.
 *
 * See docs/ui_redesign_posthog/sprint_04_navigation.html.
 */
const meta = {
  title: "Legacy / HeaderBar",
  component: HeaderBar,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof HeaderBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithInvestigationChip: Story = {
  args: {
    children: (
      <span className="text-xs font-mono text-stone-500">
        inv: <span className="text-stone-900">inv-storybook-demo</span>
      </span>
    ),
  },
};
