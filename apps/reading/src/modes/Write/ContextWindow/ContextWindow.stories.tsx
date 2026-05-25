import type { Meta, StoryObj } from "@storybook/react";

import { ContextWindow } from "./ContextWindow";

/**
 * ContextWindow — the pre-outline, outline-optional path (specs/write/
 * SPR-08). Drop blocks, state an objective, generate directly (promote →
 * generate, reusing SPR-06's citation + gate + gap contract). Network
 * calls hit `/write/*`; with no backend they fail soft.
 */
const meta = {
  title: "Write / ContextWindow",
  component: ContextWindow,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof ContextWindow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="h-screen bg-ice-2 dark:bg-space-2 p-6">
      <div className="w-full max-w-2xl mx-auto bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night">
        <ContextWindow />
      </div>
    </div>
  ),
};
