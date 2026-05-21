import type { Meta, StoryObj } from "@storybook/react";

import VoiceBlock from "./VoiceBlock";
import type { PerDocNotebookBlock } from "../../../../api/notebooks/by-doc";

/**
 * voice_block — sourced from ``voice_note_recorded``. Inline play
 * button defers to SPR-05's playback component when wired; in
 * Storybook onVoicePlay logs to console.
 */
const meta = {
  title: "Loop 2 / Notebook Blocks / VoiceBlock",
  component: VoiceBlock,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof VoiceBlock>;

export default meta;
type Story = StoryObj<typeof meta>;

const base: PerDocNotebookBlock = {
  block_id: "blk-v-abc",
  notebook_id: "nbk-story",
  block_type: "voice_block",
  source_event_ids: ["evt-storybook-v-1"],
  document_id: "doc-storybook",
  content_json: {
    voice_note_id: "vn-1",
    duration_s: 11.4,
    transcript_present: true,
    anchored_to_highlight_id: "hl-anchor-99",
  },
  position: 1.0,
  demoted_at: null,
  edited_at: null,
  created_at: "2026-05-21T10:00:00Z",
};

export const Default: Story = { args: { block: base } };

export const Unanchored: Story = {
  args: {
    block: {
      ...base,
      content_json: { ...base.content_json, anchored_to_highlight_id: null },
    },
  },
};

export const TranscriptPending: Story = {
  args: {
    block: {
      ...base,
      content_json: { ...base.content_json, transcript_present: false },
    },
  },
};
