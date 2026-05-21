// SPR-05 / M7 — Storybook story for VoiceGlyph (idle state).

import type { Meta, StoryObj } from "@storybook/react";

import VoiceGlyph from "./VoiceGlyph";

const meta = {
  title: "Wrestle / VoiceGlyph",
  component: VoiceGlyph,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof VoiceGlyph>;

export default meta;
type Story = StoryObj<typeof meta>;

const fakeAnchor = {
  anchor_id: "vna-storybook-0001",
  voice_note_id: "doc-vn-storybook",
  document_id: "doc-src-storybook",
  page: 0,
  bbox: { x0: 50, y0: 80, x1: 250, y1: 160 },
  chunk_id: null,
  chunker_version: "storybook",
  created_at: new Date().toISOString(),
};

export const Idle: Story = {
  args: {
    anchor: fakeAnchor,
    top: 120,
    left: 40,
    transcriptSnippet:
      "Operator's voice note about this passage — a quick reaction to the claim about residual stream norms.",
    onOpenPlayback: () => undefined,
  },
};
