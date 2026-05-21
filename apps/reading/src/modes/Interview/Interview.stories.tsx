import type { Meta, StoryObj } from "@storybook/react";

import InterviewMode from "./index";

/**
 * Loop 4 interview surface (master-spec §11.5) — three-pane
 * conversation UI with consent state, running transcript, compose
 * inputs for interviewer/informant turns, and embedded voice
 * capture.
 *
 * Storybook renders the loading/error state (no backend → no
 * interview_id resolves). Real interaction flows are exercised
 * server-side via the interview-projects + /interviews/{id}/turn
 * endpoint tests.
 */
const meta = {
  title: "Workstation / Interview",
  component: InterviewMode,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof InterviewMode>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LoadingState: Story = {};
