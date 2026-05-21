import type { Meta, StoryObj } from "@storybook/react";

import type { Event } from "../generated/types";
import CrossDocSidebar from "./CrossDocSidebar";

/**
 * CrossDocSidebar renders cross_doc.question_answered events with
 * the bridging note linkage. Master-spec §4.2 cross-mode connection
 * (Loop 2 Sprint 4 day 2-3 cross-doc linking; Sprint 17 included for
 * design-system documentation).
 */
const meta = {
  title: "Loop 2 / CrossDocSidebar",
  component: CrossDocSidebar,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof CrossDocSidebar>;

export default meta;
type Story = StoryObj<typeof meta>;

function questionIdentified(id: string, text: string): Event {
  return {
    event_id: `evt-q-${id}`,
    investigation_id: "inv-storybook-demo",
    document_id: "doc-quantum-paper-1",
    action_type: "question.identified",
    emitted_at: new Date().toISOString(),
    role: "note_taker",
    payload: {
      action_type: "question.identified",
      question_id: id,
      question_text: text,
    } as never,
  } as Event;
}

function crossDocLink(qid: string): Event {
  return {
    event_id: `evt-link-${qid}`,
    investigation_id: "inv-storybook-demo",
    document_id: null,
    action_type: "cross_doc.question_answered",
    emitted_at: new Date().toISOString(),
    role: "note_taker",
    payload: {
      action_type: "cross_doc.question_answered",
      question_id: qid,
      question_document_id: "doc-quantum-paper-1",
      answer_document_id: "doc-quantum-paper-2",
      answer_note_id: `n-answer-${qid}`,
    } as never,
  } as Event;
}

export const SingleCrossDocLink: Story = {
  args: {
    events: [
      questionIdentified(
        "q-1",
        "How does the Lukin gate-set compare to the Vuletic preprint?",
      ),
      crossDocLink("q-1"),
    ],
  },
};

export const Empty: Story = {
  args: { events: [] },
};
