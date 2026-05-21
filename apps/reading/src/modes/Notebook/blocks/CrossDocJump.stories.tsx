import type { Meta, StoryObj } from "@storybook/react";

import CrossDocJump from "./CrossDocJump";
import type { PerDocNotebookBlock } from "../../../../api/notebooks/by-doc";

/** cross_doc_jump — sourced from ``cross_doc_link_clicked``. */
const meta = {
  title: "Loop 2 / Notebook Blocks / CrossDocJump",
  component: CrossDocJump,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof CrossDocJump>;

export default meta;
type Story = StoryObj<typeof meta>;

const base: PerDocNotebookBlock = {
  block_id: "blk-x-abc",
  notebook_id: "nbk-story",
  block_type: "cross_doc_jump",
  source_event_ids: ["evt-xdoc-1"],
  document_id: "doc-storybook",
  content_json: {
    link_id: "link-abc",
    target_document_id: "doc-target-clicked",
    target_chunk_id: "chk-target-1",
    elapsed_since_surfaced_s: 4.7,
  },
  position: 1.0,
  demoted_at: null,
  edited_at: null,
  created_at: "2026-05-21T10:00:00Z",
};

export const QuickClick: Story = { args: { block: base } };

export const SlowClick: Story = {
  args: {
    block: {
      ...base,
      content_json: {
        ...base.content_json,
        elapsed_since_surfaced_s: 42.3,
      },
    },
  },
};
