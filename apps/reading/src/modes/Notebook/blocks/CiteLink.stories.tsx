import type { Meta, StoryObj } from "@storybook/react";

import CiteLink from "./CiteLink";
import type { PerDocNotebookBlock } from "../../../../api/notebooks/by-doc";

/** cite_link — sourced from ``cite_jump``. Click → cite-jump via the
 * SPR-07 deep-link path. */
const meta = {
  title: "Loop 2 / Notebook Blocks / CiteLink",
  component: CiteLink,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof CiteLink>;

export default meta;
type Story = StoryObj<typeof meta>;

const base: PerDocNotebookBlock = {
  block_id: "blk-c-abc",
  notebook_id: "nbk-story",
  block_type: "cite_link",
  source_event_ids: ["evt-cite-1"],
  document_id: "doc-storybook",
  content_json: {
    target_document_id: "doc-target-2026-fault-tolerance",
    target_chunk_id: "chk-abc999",
    direction: "forward",
    source_chunk_id: "chk-xyz111",
  },
  position: 1.0,
  demoted_at: null,
  edited_at: null,
  created_at: "2026-05-21T10:00:00Z",
};

export const Forward: Story = { args: { block: base } };

export const Backward: Story = {
  args: {
    block: {
      ...base,
      content_json: { ...base.content_json, direction: "backward" },
    },
  },
};

export const UnresolvedTarget: Story = {
  args: {
    block: {
      ...base,
      content_json: { ...base.content_json, target_document_id: null },
    },
  },
};
