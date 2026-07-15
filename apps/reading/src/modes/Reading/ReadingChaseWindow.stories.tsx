import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import ReadingChaseWindow from "./ReadingChaseWindow";

const meta = {
  title: "Reading/Chase window",
  component: ReadingChaseWindow,
  decorators: [(Story) => <MemoryRouter><div className="h-[620px] w-[500px] bg-ice-0"><Story /></div></MemoryRouter>],
  args: {
    spawnContext: "A knowledge system becomes useful when every conclusion keeps a visible path back to its evidence.",
    parentInvestigationId: "read-designing-knowledge",
    documentTitle: "Designing Knowledge Systems",
    pageNumber: 42,
    workspaceWindowId: "story-reading-chase",
  },
} satisfies Meta<typeof ReadingChaseWindow>;

export default meta;
type Story = StoryObj<typeof meta>;
export const ReadyToFollow: Story = {};
