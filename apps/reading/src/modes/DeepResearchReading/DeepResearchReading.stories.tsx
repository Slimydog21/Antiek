import type { Meta, StoryObj } from "@storybook/react";

import type { DocumentGap, DocumentNote } from "../../api/reading";
import DocumentView from "./DocumentView";
import GapSidebar from "./GapSidebar";
import NoteCard from "./NoteCard";

const meta = {
  title: "DeepResearch / Reading",
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const RAW =
  "# Web-gaming wedge\n\nGPUs gate model scale, and inference cost dominates unit economics. " +
  "Capital is abundant in this market. The behavioral-moderation problem is unsolved at scale.";

const NOTES: DocumentNote[] = [
  { node_id: "i1", kind: "insight", text: "Inference cost dominates unit economics.", confidence: "high",
    anchors: ["GPUs gate model scale, and inference cost dominates unit economics."] },
  { node_id: "q1", kind: "question", text: "How does behavioral moderation scale?", confidence: "unknown",
    anchors: ["The behavioral-moderation problem is unsolved at scale."] },
];

const GAPS: DocumentGap[] = [
  { gap_id: "gap-1", kind: "unanswered_question", question: "How does behavioral moderation scale at 10M DAU?", impact_score: 0.82, backing_node_ids: ["q1"] },
  { gap_id: "gap-2", kind: "unsupported_claim", question: "Find evidence: capital is abundant in this market.", impact_score: 0.4, backing_node_ids: ["i1"] },
];

export const Document_With_Highlights: Story = {
  render: () => (
    <div className="h-[420px]">
      <DocumentView rawText={RAW} notes={NOTES} selectedNoteId="i1"
        onSelectNote={() => {}} onSaveEdit={() => {}} />
    </div>
  ),
};

export const Note_Card: Story = {
  render: () => (
    <div className="flex w-80 flex-col gap-3">
      {NOTES.map((n) => <NoteCard key={n.node_id} note={n} documentId="doc-1" />)}
      <NoteCard note={{ ...NOTES[0], node_id: "stale" }} documentId="doc-1" stale />
    </div>
  ),
};

export const Gap_Sidebar: Story = {
  render: () => (
    <div className="w-80">
      <GapSidebar gaps={GAPS} onSpin={() => {}} />
    </div>
  ),
};
