import type { Meta, StoryObj } from "@storybook/react";

import Home from "./Home";

/**
 * Home (SPR-12 M1) — the unified branded front door.
 *
 * One branded statement of what Antiek is, four equal doors (one click into
 * each surface), biographies featured with an honest "still on its way"
 * label for the unbuilt SPR-11 guided flow. The global preview wraps every
 * story in a router, so navigation in the cards is harmless here.
 *
 * Visual baseline coverage: the home in light + dark (the top-left Werner
 * mark renders with the M4 alpha-cut pose, so there is no white box behind
 * it in the hero either).
 */
const meta = {
  title: "Home / Unified home (SPR-12)",
  component: Home,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof Home>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="h-screen w-screen">
      <Home />
    </div>
  ),
};
