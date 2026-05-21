import type { Meta, StoryObj } from "@storybook/react";

import HighlightCard from "./HighlightCard";
import type { PerDocNotebookBlock } from "../../../../api/notebooks/by-doc";

/**
 * highlight_card — sourced from a Tier-1 ``highlight_created`` event.
 * The block shows the captured passage + tag + cite-jump back to the
 * source chunk. Operator framing prose hangs off the BlockShell
 * footer. Per services/notebooks/BLOCK_TAXONOMY.md: no "+ new block"
 * affordance; this block exists only because the user highlighted
 * something.
 */
const meta = {
  title: "Loop 2 / Notebook Blocks / HighlightCard",
  component: HighlightCard,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof HighlightCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const baseBlock: PerDocNotebookBlock = {
  block_id: "blk-h-abc123",
  notebook_id: "nbk-story-1",
  block_type: "highlight_card",
  source_event_ids: ["evt-storybook-h-1"],
  document_id: "doc-storybook",
  content_json: {
    passage_text:
      "Neutral-atom platforms have demonstrated single-qubit gate " +
      "error rates below 10⁻³, consistent with the threshold thesis " +
      "for fault-tolerant operation.",
    chunk_id: "chk-12345",
    color: "yellow",
    tag: "fault-tolerance",
    highlight_id: "hl-storybook-1",
    operator_framing: "",
  },
  position: 1.0,
  demoted_at: null,
  edited_at: null,
  created_at: "2026-05-21T10:00:00Z",
};

export const Default: Story = {
  args: {
    block: baseBlock,
    onCiteJump: (doc, chunk) =>
      // eslint-disable-next-line no-alert
      alert(`cite-jump to ${doc} / ${chunk}`),
  },
};

export const WithOperatorFraming: Story = {
  args: {
    block: {
      ...baseBlock,
      content_json: {
        ...baseBlock.content_json,
        operator_framing:
          "This is the linchpin claim for the SPR-17 backtest gate — " +
          "if neutral-atom error rates hold below 10⁻³ at 1000+ qubits, " +
          "the post-quantum security timeline shortens by ~2 years.",
      },
    },
    onEditFraming: () => undefined,
  },
};

export const Demoted: Story = {
  args: {
    block: { ...baseBlock, demoted_at: "2026-05-21T11:00:00Z" },
    onDemote: () => undefined,
  },
};

export const NoChunkId: Story = {
  args: {
    block: {
      ...baseBlock,
      content_json: { ...baseBlock.content_json, chunk_id: null },
    },
  },
};
