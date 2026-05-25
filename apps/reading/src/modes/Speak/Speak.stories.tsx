import type { Meta, StoryObj } from "@storybook/react";

import SpeakConsole from "./index";

/**
 * Speak project console (specs/speak/) — the operator's per-project
 * workspace: invites, corroborate, draft, publish, with gate-refusal
 * feedback.
 *
 * Storybook renders it without a route param, so it shows the
 * no-project-selected guidance (the console reads :projectId from the
 * router; the global MemoryRouter decorator has no param here). The
 * live, parameterised flow is exercised end-to-end in
 * tests/test_speak_api.py.
 */
const meta = {
  title: "Workstation / Speak / Console",
  component: SpeakConsole,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof SpeakConsole>;

export default meta;
type Story = StoryObj<typeof meta>;

export const NoProjectSelected: Story = {};
