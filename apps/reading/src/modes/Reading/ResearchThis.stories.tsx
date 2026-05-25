import type { Meta, StoryObj } from "@storybook/react";

import ResearchThis from "./ResearchThis";

/**
 * The spin-research affordance (Read SPR-08). Clicking builds a gate-safe
 * seed server-side and hands off to the Research workflow. (Storybook has
 * no backend, so clicking surfaces the graceful error — the same state a
 * reader sees if the spin endpoint is unreachable.)
 */
const meta = {
  title: "Read / ResearchThis",
  component: ResearchThis,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ResearchThis>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { documentId: "doc-book-1", pageIndex: 3, passageText: "A selected passage worth researching." },
};
