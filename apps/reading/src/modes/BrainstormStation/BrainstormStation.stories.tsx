import type { Meta, StoryObj } from "@storybook/react";

import type { ParkedQuestionEntry } from "../../lib/api";
import BrainstormStation from "./index";

const questions: ParkedQuestionEntry[] = [
  {
    question_id: "q-market-map",
    question_text: "What evidence would make the market map obsolete rather than merely incomplete?",
    source_investigation_id: "inv-autonomous-research",
    source_document_id: "doc-market-map",
    anchor_region_id: "region-14",
    parked_at: "2026-07-15T18:00:00Z",
    parent_event_id: "event-14",
  },
  {
    question_id: "q-routing",
    question_text: "Where does model routing improve research quality, and where does it only hide uncertainty?",
    source_investigation_id: "inv-model-routing",
    source_document_id: null,
    anchor_region_id: null,
    parked_at: "2026-07-14T16:00:00Z",
    parent_event_id: "event-9",
  },
];

const never = () => new Promise<never>(() => undefined);
const meta = {
  title: "Brainstorm / Curiosity Observatory",
  component: BrainstormStation,
  decorators: [(Story) => <div className="h-screen"><Story /></div>],
  parameters: {
    layout: "fullscreen",
    // Give the full-bleed authored raster time to decode and settle before
    // Chromium captures it at three independently scaled breakpoints.
    lostpixel: { waitBeforeScreenshot: 3000 },
  },
  tags: ["a11y-audit"],
  args: { withWorkspacePanels: false, animateAmbience: false },
} satisfies Meta<typeof BrainstormStation>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Populated: Story = {
  args: { loadQuestions: async () => ({ count: questions.length, questions }) },
};

export const Empty: Story = {
  args: { loadQuestions: async () => ({ count: 0, questions: [] }) },
};

export const Loading: Story = {
  args: { loadQuestions: never },
};

export const Error: Story = {
  args: { loadQuestions: async () => { throw new Error("fixture failure"); } },
};
