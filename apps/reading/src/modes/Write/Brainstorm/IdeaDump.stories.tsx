import type { Meta, StoryObj } from "@storybook/react";

import { IdeaDump } from "./IdeaDump";

/**
 * IdeaDump — the brainstorm-interview surface (specs/write/ SPR-05). Dump
 * an idea, review the driving insights/questions/data (asserted data
 * flagged to verify), run a turn-capped clarification loop, emit
 * brainstorm-originated lego blocks. Network calls hit `/write/*`.
 */
const meta = {
  title: "Write / IdeaDump",
  component: IdeaDump,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: { sectionId: "story-sec", deliverableId: "story-dlv" },
} satisfies Meta<typeof IdeaDump>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args) => (
    <div className="h-screen bg-ice-2 dark:bg-space-2 p-6">
      <div className="w-full max-w-3xl mx-auto bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night">
        <IdeaDump {...args} />
      </div>
    </div>
  ),
};
