import type { Meta, StoryObj } from "@storybook/react";

import InterviewTranscript from "./InterviewTranscript";

/**
 * Speak SPR-02 M5 — transcript correction.
 *
 * ASR mishears names, places, and dates — the biographical details
 * that matter most. A `pending` informant turn (transcribed, not yet
 * distilled) is editable; distillation runs from the corrected text,
 * never the raw one. These stories seed turns directly (no backend).
 */
const meta = {
  title: "Workstation / Interview / Transcript",
  component: InterviewTranscript,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof InterviewTranscript>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A distilled, settled transcript — no pending corrections. */
export const Settled: Story = {
  args: {
    interviewId: "interview-demo",
    seedTurns: [
      {
        role: "interviewer",
        text: "What is your earliest memory of him?",
        ts: "2026-05-25T10:00:00Z",
        question_id: "q1",
      },
      {
        role: "informant",
        text: "The smell of his workshop in winter — sawdust and coffee.",
        ts: "2026-05-25T10:02:00Z",
        question_id: "q1",
      },
    ],
  },
};

/**
 * A freshly-transcribed answer awaiting correction: ASR heard "Kyro".
 * The interviewee clicks "correct" and fixes it to "Cairo" before it is
 * distilled into the graph.
 */
export const PendingCorrection: Story = {
  args: {
    interviewId: "interview-demo",
    onCorrect: (index, text) =>
      // eslint-disable-next-line no-console
      console.log(`corrected turn ${index} → ${text}`),
    seedTurns: [
      {
        role: "interviewer",
        text: "Where was he born?",
        ts: "2026-05-25T10:05:00Z",
        question_id: "q2",
      },
      {
        role: "informant",
        text: "He was born in Kyro in 1940.",
        ts: "2026-05-25T10:06:00Z",
        question_id: "q2",
        pending: true,
      },
    ],
  },
};
