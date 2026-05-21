// SPR-05 / M7 — Storybook story for the playback overlay.

import type { Meta, StoryObj } from "@storybook/react";

import VoicePlayback from "./VoicePlayback";

const meta = {
  title: "Wrestle / VoicePlayback",
  component: VoicePlayback,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof VoicePlayback>;

export default meta;
type Story = StoryObj<typeof meta>;

const fakeAnchor = {
  anchor_id: "vna-storybook-0002",
  voice_note_id: "doc-vn-storybook",
  document_id: "doc-src-storybook",
  page: 0,
  bbox: { x0: 50, y0: 80, x1: 250, y1: 160 },
  chunk_id: null,
  chunker_version: "storybook",
  created_at: new Date().toISOString(),
};

const SAMPLE_TRANSCRIPT = `The thing this paragraph is missing is the connection between
residual stream norms and the optimization landscape. The claim is
that growing norms imply harder optimization, but the citation
chain doesn't establish the second half — it shows the
correlation, not the causal direction.`;

export const Active: Story = {
  args: {
    anchor: fakeAnchor,
    anchorTop: 240,
    anchorLeft: 320,
    // Empty src; in storybook we just want to see the overlay
    // chrome, not actual audio.
    audioUrl: "",
    transcript: SAMPLE_TRANSCRIPT,
    onClose: () => undefined,
  },
};
