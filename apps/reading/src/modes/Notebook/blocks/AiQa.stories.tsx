import type { Meta, StoryObj } from "@storybook/react";

import AiQa from "./AiQa";
import type { PerDocNotebookBlock } from "../../../../api/notebooks/by-doc";

/** ai_qa — sourced from ``ai_response_accepted``. Pairs with the
 * matching ``ai_prompt_sent`` for the question text via prompt_id. */
const meta = {
  title: "Loop 2 / Notebook Blocks / AiQa",
  component: AiQa,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof AiQa>;

export default meta;
type Story = StoryObj<typeof meta>;

const base: PerDocNotebookBlock = {
  block_id: "blk-a-abc",
  notebook_id: "nbk-story",
  block_type: "ai_qa",
  source_event_ids: ["evt-prompt-1", "evt-resp-1"],
  document_id: "doc-storybook",
  content_json: {
    prompt_id: "p-1",
    response_id: "r-1",
    accept_kind: "pinned",
    prompt_text:
      "Summarise the threshold-thesis argument the section makes for " +
      "neutral-atom fault tolerance in three sentences.",
    prompt_missing: false,
  },
  position: 1.0,
  demoted_at: null,
  edited_at: null,
  created_at: "2026-05-21T10:00:00Z",
};

export const Default: Story = { args: { block: base } };

export const PromptMissing: Story = {
  args: {
    block: {
      ...base,
      content_json: {
        ...base.content_json,
        prompt_text: null,
        prompt_missing: true,
      },
    },
  },
};

export const AcceptKindApplied: Story = {
  args: {
    block: {
      ...base,
      content_json: { ...base.content_json, accept_kind: "applied" },
    },
  },
};
