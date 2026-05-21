import type { Meta, StoryObj } from "@storybook/react";

import Loop3 from "./index";

/**
 * Loop3 checklist page (master-spec §14.2 + §13.7).
 *
 * Operator surface for the five RL-unlock criteria. Per the binding
 * gate: criteria-met ≠ training-authorized. The env-var
 * ANTIEK_LOOP3_UNLOCKED=1 is the operator's separate, final action.
 *
 * Stories render the full page. The backend fetch
 * (GET /loop-3/status) fails silently in Storybook (no server) so
 * the page renders the loading state and stays there. Real
 * interaction is exercised via the unit tests at
 * tests/test_loop_3_checklist_and_rubric.py.
 */
const meta = {
  title: "PostHog Wedges / Loop3 checklist",
  component: Loop3,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Loop3>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Default story — page renders in its loading state because
 * Storybook has no backend. The story is still useful as a visual
 * regression target for the page chrome (header, description, tiles
 * placeholder).
 */
export const Default: Story = {};
