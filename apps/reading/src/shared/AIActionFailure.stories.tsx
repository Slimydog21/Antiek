import type { Meta, StoryObj } from "@storybook/react";

import AIActionFailure from "./AIActionFailure";

/**
 * AIActionFailure (U-04) — the one honest-failure surface across the four doors.
 *
 * Stories cover the three states the spec names:
 *   - failure WITH an engine reason (the diagnostic is framed, not raw prose),
 *   - failure WITHOUT a reason (the honest no-provider/credential sentence),
 *   - the retrying state (the action re-runs in place; this never navigates).
 *
 * Werner skin (Lemon tokens) — no hardcoded colors.
 */
const meta = {
  title: "Shared / AIActionFailure (U-04)",
  component: AIActionFailure,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
  args: {
    title: "The research didn’t complete",
    onRetry: () => {},
  },
} satisfies Meta<typeof AIActionFailure>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * A failure the engine explained — the lead is generic ("the engine reported
 * a problem"), and the engine's own reason is shown framed below as the
 * diagnostic. We don't assert a specific cause above the contradicting truth.
 */
export const WithReason: Story = {
  args: { reason: "no model provider configured" },
};

/** A reason-less failure — the honest no-provider/credential sentence stands alone. */
export const WithoutReason: Story = {
  args: { reason: null },
};

/** Retrying — the same surface; the caller re-runs the action in place. */
export const Retrying: Story = {
  args: {
    reason: "provider keys missing",
    retryLabel: "Retrying…",
  },
};
