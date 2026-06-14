import type { Meta, StoryObj } from "@storybook/react";

import WorkflowStub from "./WorkflowStub";

/**
 * WorkflowStub (SPR-04 M5) — the honest "not yet" surface for a workflow whose
 * product isn't built. The honesty contract: it never presents absent
 * capability as present, and it is LOUD on misuse (rendering a "this is built"
 * note if called for a built workflow) rather than silently lying.
 *
 * ── States authored (ALC SPR-09 product-character lift) ──────────────────────
 * WorkflowStub renders two reachable states off real inputs — the honest
 * unbuilt placeholder (its reason for existing) and the loud misuse guard. Each
 * is a named story driving the REAL component (the `forceUnbuiltForStory` flag
 * is the component's own documented Storybook/test lever for the unbuilt
 * branch, since every real workflow has a built surface on the live tree).
 *
 * Honesty note (intellectual honesty #1): the component ALSO renders a "Pending
 * surfaces" list, but on the live taxonomy NO non-shared workflow has an
 * unbuilt mode (every research/read/write/speak mode is `built: true`), so that
 * branch is currently unreachable for these four workflows from real data. It
 * is deliberately NOT authored as a story rather than faked by mutating the
 * taxonomy — when a future workflow ships with a pending sub-surface, the list
 * appears under the Unbuilt story and a dedicated state can be added then.
 *
 * Werner skin (Lemon tokens) — no hardcoded colors.
 */
const meta = {
  title: "Shell / WorkflowStub (SPR-04)",
  component: WorkflowStub,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof WorkflowStub>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * UNBUILT — the default honest state: "Not yet — <workflow> is on the way",
 * the tagline, and the shipping sprint. Forced into the unbuilt branch via the
 * component's documented story-only flag so the state is inspectable even
 * though the workflow has a built surface today.
 */
export const Unbuilt: Story = {
  args: { workflow: "write", forceUnbuiltForStory: true },
  render: (args) => {
    return (
      <div className="h-screen bg-ice-2 dark:bg-space-2">
        <WorkflowStub {...args} />
      </div>
    );
  },
};

/**
 * MISUSE GUARD — the loud failure state. Rendered for a BUILT workflow WITHOUT
 * the force flag, so the component surfaces "This workflow has built surfaces —
 * render its scene, not this stub" instead of silently lying. Authored so the
 * honest-failure branch is inspectable, not just the happy placeholder.
 */
export const MisuseGuard: Story = {
  args: { workflow: "research" },
  render: (args) => {
    return (
      <div className="h-screen bg-ice-2 dark:bg-space-2">
        <WorkflowStub {...args} />
      </div>
    );
  },
};
