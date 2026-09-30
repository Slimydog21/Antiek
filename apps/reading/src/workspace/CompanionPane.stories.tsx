import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";

import CompanionPane from "./CompanionPane";
import { useCompanion } from "./companionStore";

/**
 * CompanionPane's agent strip at the pane's own width (lane A B3-1): three
 * agents fit; twelve scroll sideways behind edge fades, with the ⋯ menu
 * (searchable past eight) listing every agent and "+ new agent" always at
 * the end of the row. The pane's content never scrolls sideways. Day and
 * night, at the inset's 320 px and the md tier's full-width pane.
 */
const QUESTIONS = [
  "Did beak depth in Darwin's finches track the 1977 drought?",
  "How much of Origin's argument leans on Malthus?",
  "Where does Lyell's uniformitarianism enter chapter 9?",
  "Was the shift heritable or plastic?",
  "Who first measured Geospiza fortis beaks?",
  "What did Lack's 1947 monograph get wrong?",
  "Is character displacement visible on Daphne Major?",
  "Which seeds failed first in the drought?",
  "How big was the 1978 cohort?",
  "Did Wallace read Malthus before Darwin?",
  "What does 'descent with modification' add to Lamarck?",
  "Where is the tree-of-life figure argued?",
];

function StoryPane({ agents, width }: { agents: number; width: number }) {
  // Seed the store once, before the first render of the pane.
  useState(() => {
    const store = useCompanion.getState();
    store.reset();
    for (let i = 0; i < agents; i++) {
      store.openAgentTab({ kind: "research-thread", investigationId: `story-${i}`, title: QUESTIONS[i % QUESTIONS.length] });
    }
    return null;
  });
  return (
    <MemoryRouter>
      <div className="p-4" style={{ background: "var(--bg-page)" }}>
        <div
          data-pane="right"
          className="flex h-[420px] flex-col overflow-hidden rounded-lg border border-hairline bg-ice-1 dark:bg-charcoal-1"
          style={{ width }}
        >
          <CompanionPane />
        </div>
      </div>
    </MemoryRouter>
  );
}

const meta = {
  title: "Workspace/CompanionPane",
  component: StoryPane,
  args: { agents: 3, width: 320 },
} satisfies Meta<typeof StoryPane>;
export default meta;

type Story = StoryObj<typeof meta>;

const day = { theme: "light" } as const;
const night = { theme: "dark" } as const;

export const ThreeAgentsDay: Story = { args: { agents: 3, width: 320 }, globals: day };
export const ThreeAgentsNight: Story = { args: { agents: 3, width: 320 }, globals: night };
export const TwelveAgentsDay: Story = { args: { agents: 12, width: 320 }, globals: day };
export const TwelveAgentsNight: Story = { args: { agents: 12, width: 320 }, globals: night };
export const TwelveAgentsMdPaneDay: Story = { args: { agents: 12, width: 860 }, globals: day };
