import type { Meta, StoryObj } from "@storybook/react";

import InterviewVoiceCapture from "./InterviewVoiceCapture";

/**
 * InterviewVoiceCapture — captures audio for an interview session and
 * uploads on stop. The component drives a MediaRecorder internally; in
 * Storybook the recorder will be unavailable unless mic permission is
 * granted in the iframe, so this story documents the visual state only.
 */
const meta = {
  title: "Loop 5 / InterviewVoiceCapture",
  component: InterviewVoiceCapture,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof InterviewVoiceCapture>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    buildUploadUrl: (duration) =>
      `/speak/invite/storybook-token/voice?question_id=storybook-question&duration_seconds=${duration}`,
    onUploaded: (clipId) => alert(`uploaded: ${clipId}`),
  },
};
