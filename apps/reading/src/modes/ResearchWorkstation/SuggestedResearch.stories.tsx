import type { Meta, StoryObj } from "@storybook/react";

import type { Suggestion } from "../../api/research";
import {
  SuggestedResearchFrame,
  SuggestionCard,
  type SuggestedChase,
} from "./SuggestedResearch";

const THREADS: Suggestion[] = [
  {
    key: "thread-fisheries",
    question: "Which Pacific fisheries carry the greatest exposure to new seabed-mining corridors?",
    suggested_retrieval: "Compare EEZ maps with tuna migration and license-area boundaries",
    seen_in_research_count: 4,
    source_investigation_id: "inv-pacific-mining",
  },
  {
    key: "thread-compensation",
    question: "What compensation precedents exist when extraction harms a transboundary commons?",
    suggested_retrieval: "Review ISA benefit-sharing proposals and analogous maritime settlements",
    seen_in_research_count: 2,
    source_investigation_id: "inv-pacific-mining",
  },
];

function Preview({ variant = "lane", canLaunch = true }: { variant?: "lane" | "beside"; canLaunch?: boolean }) {
  const handOff = (_chase: SuggestedChase) => {};
  return (
    <SuggestedResearchFrame variant={variant}>
      <div className={variant === "beside" ? "space-y-2" : "space-y-3"}>
        {THREADS.map((suggestion, index) => (
          <SuggestionCard
            key={suggestion.key}
            suggestion={suggestion}
            threadNumber={index + 1}
            canLaunch={canLaunch}
            onChaseGesture={handOff}
            onLaunched={() => {}}
          />
        ))}
      </div>
    </SuggestedResearchFrame>
  );
}

const meta = {
  title: "ResearchWorkstation / Suggested research thread cards",
  component: Preview,
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <main className="min-h-screen bg-ice-0 p-4 text-ink dark:bg-charcoal-2 dark:text-bright md:p-8">
        <h1 className="sr-only">Suggested research thread cards</h1>
        <div className="mx-auto max-w-5xl">
          <Story />
        </div>
      </main>
    ),
  ],
} satisfies Meta<typeof Preview>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Lane: Story = { args: { variant: "lane", canLaunch: true } };
export const BesideAnswer: Story = { args: { variant: "beside", canLaunch: true } };
export const SignedOut: Story = { args: { variant: "lane", canLaunch: false } };
