import type { Meta, StoryObj } from "@storybook/react";

import { Repository } from "./Repository";

/**
 * Repository — the Write block repository (specs/write/ SPR-03). The
 * supply side: cross-investigation folders (views over nodes) + search,
 * each result a drag source for the outline.
 *
 * Network calls hit `/write/*`; with no backend they fail soft (empty
 * state), so these stories render standalone — the empty + populated
 * states are what a reviewer checks visually.
 */
const meta = {
  title: "Write / Repository",
  component: Repository,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof Repository>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="h-screen bg-ice-2 dark:bg-space-2 p-6">
      <div className="w-full max-w-4xl mx-auto h-[80vh] bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night p-4">
        <Repository />
      </div>
    </div>
  ),
};
