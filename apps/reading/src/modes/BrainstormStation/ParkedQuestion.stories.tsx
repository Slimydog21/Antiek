import type { Meta, StoryObj } from "@storybook/react";

import type { ParkedQuestionEntry } from "../../lib/api";
import ParkedQuestion from "./ParkedQuestion";

/**
 * Selected parked-question detail pane in the Brainstorming
 * Workstation (Surface E, master-spec §4.5). Shows the question
 * text + source context + launch affordance. The launch button
 * POSTs to /watch-for-later/{question_id}/launch which spawns a
 * child investigation and emits question.escalated_to_research
 * so the folder hides the question on next refresh.
 */
const meta = {
  title: "Surface E — Brainstorm / ParkedQuestion",
  component: ParkedQuestion,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof ParkedQuestion>;

export default meta;
type Story = StoryObj<typeof meta>;

const baseQuestion: ParkedQuestionEntry = {
  question_id: "q-quantum-001",
  question_text:
    "How does the Lukin lab's gate-set decomposition compare head-to-head with the Vuletic preprint when normalized for circuit depth?",
  source_investigation_id: "inv-a1b2c3d4e5f6",
  source_document_id: "doc-vuletic-2025",
  anchor_region_id: "reg-7890",
  parked_at: "2026-05-19T12:34:56.789Z",
  parent_event_id: "evt-q-quantum-001",
};

export const Default: Story = {
  args: {
    question: baseQuestion,
    launching: false,
    onLaunch: () => {},
  },
};

export const Launching: Story = {
  args: {
    question: baseQuestion,
    launching: true,
    onLaunch: () => {},
  },
};

export const MinimalContext: Story = {
  args: {
    question: {
      ...baseQuestion,
      source_document_id: null,
      anchor_region_id: null,
    },
    launching: false,
    onLaunch: () => {},
  },
};
