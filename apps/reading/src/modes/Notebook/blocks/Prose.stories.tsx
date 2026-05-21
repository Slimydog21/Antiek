import type { Meta, StoryObj } from "@storybook/react";

import Prose from "./Prose";
import type { PerDocNotebookBlock } from "../../../../api/notebooks/by-doc";

/**
 * prose — operator-editable text envelope. Auto-populator does NOT
 * emit standalone prose; this block only exists wrapped around
 * another block (via the BlockShell framing). The Orphan story
 * demonstrates the no-authoring guard.
 */
const meta = {
  title: "Loop 2 / Notebook Blocks / Prose",
  component: Prose,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof Prose>;

export default meta;
type Story = StoryObj<typeof meta>;

const base: PerDocNotebookBlock = {
  block_id: "blk-p-abc",
  notebook_id: "nbk-story",
  block_type: "prose",
  source_event_ids: ["evt-source-h-1"],
  document_id: "doc-storybook",
  content_json: {
    text:
      "Operator framing: This highlight is the linchpin claim for " +
      "the SPR-17 backtest gate. Three sentences of context the " +
      "operator added when they reopened the notebook.",
  },
  position: 1.0,
  demoted_at: null,
  edited_at: "2026-05-21T11:30:00Z",
  created_at: "2026-05-21T10:00:00Z",
};

export const Default: Story = { args: { block: base } };

export const Orphan: Story = {
  /** Demonstrates the no-authoring guard: a prose block with no
   * source_event_ids renders an inline warning rather than silently
   * accepting a free-text block.
   */
  args: {
    block: { ...base, source_event_ids: [] },
  },
};
