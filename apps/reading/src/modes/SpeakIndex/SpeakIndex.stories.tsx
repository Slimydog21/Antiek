import type { Meta, StoryObj } from "@storybook/react";

import SpeakIndex from "./index";

/**
 * Speak index — the operator's biography-project surface (specs/speak/).
 *
 * Storybook renders the empty state (no backend → no projects load).
 * The "new project" form is fully editable; the publish-intent select
 * surfaces the will-be-public consent/legal-gate note. A chrome
 * regression target; the live flow is exercised in
 * tests/test_speak_api.py.
 */
const meta = {
  title: "Workstation / Speak / Index",
  component: SpeakIndex,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof SpeakIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyState: Story = {};
