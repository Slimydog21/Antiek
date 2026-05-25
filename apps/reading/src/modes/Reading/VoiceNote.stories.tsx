import type { Meta, StoryObj } from "@storybook/react";

import VoiceNote from "./VoiceNote";

/**
 * Voice-note capture control (Read SPR-06). Renders the capture phase —
 * "Record a thought". The full flow (record → transcribe → CORRECT →
 * save) needs a mic + the Whisper/distill backend; in Storybook the
 * record button surfaces the graceful mic/permission path. The editable-
 * transcript correction step is the honesty guard surfaced in the UI.
 */
const meta = {
  title: "Read / VoiceNote",
  component: VoiceNote,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof VoiceNote>;

export default meta;
type Story = StoryObj<typeof meta>;

export const CapturePhase: Story = {
  args: { documentId: "doc-book-1", pageIndex: 4, investigationId: "read-doc-book-1" },
};
