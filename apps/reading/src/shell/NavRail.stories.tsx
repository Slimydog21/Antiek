import type { Meta, StoryObj } from "@storybook/react";

import NavRail from "./NavRail";
import ProjectTree from "./ProjectTree";
import SceneChrome from "./SceneChrome";
import WorkflowStub from "./WorkflowStub";

/**
 * NavRail (SPR-04) — the four-workflow content-first rail.
 *
 * Stories cover the SPR-04 acceptance surface:
 *   - the rail itself (exactly four workflows + Search/New + a single
 *     "More" footer affordance — the ⊞ launcher),
 *   - each workflow's content-first tree (zone 2),
 *   - the scene chrome (zone 3 action bar + tabs),
 *   - the honest "not yet" stub state.
 *
 * Everything renders in the Werner skin (sun-yellow edge, ink rail) using
 * Lemon tokens — pattern from PostHog-2025 content-first IA, tone is ours.
 */
const meta = {
  title: "Shell / NavRail (SPR-04)",
  component: NavRail,
  // The global Storybook preview already wraps every story in a
  // MemoryRouter, so we don't add a second (nested) router here.
  parameters: { layout: "fullscreen" },
  // `a11y-audit` opts this story into the test-runner axe gate
  // (.storybook/test-runner.ts, selected via `--includeTags a11y-audit`).
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof NavRail>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The rail alone — exactly four workflows + Search/New + a "More" footer. */
export const FourWorkflowRail: Story = {
  render: () => (
    <div className="h-screen flex bg-ice-2 dark:bg-space-2">
      <NavRail />
      <div className="flex-1 flex items-center justify-center text-ink-soft dark:text-moonlight text-sm">
        Four workflows: Research · Read · Write · Speak. Click ⊞ "More" for
        the full inventory + Operator/Trust/Settings; ⌕ for ⌘K.
      </div>
    </div>
  ),
};

/** Rail + content-first project tree (zone 2), scoped to Research. */
export const RailWithResearchTree: Story = {
  render: () => (
    <div className="h-screen flex bg-ice-2 dark:bg-space-2">
      <NavRail />
      <div className="w-[260px] border-r border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 overflow-y-auto">
        <ProjectTree workflow="research" />
      </div>
      <div className="flex-1" />
    </div>
  ),
};

/** Rail + Read tree — the workflow nouns re-scope (library/docs/notebooks). */
export const RailWithReadTree: Story = {
  render: () => (
    <div className="h-screen flex bg-ice-2 dark:bg-space-2">
      <NavRail />
      <div className="w-[260px] border-r border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 overflow-y-auto">
        <ProjectTree workflow="read" />
      </div>
      <div className="flex-1" />
    </div>
  ),
};

/** Scene chrome (zone 3) — Research action bar + in-scene tabs over a body. */
export const ResearchSceneChrome: Story = {
  render: () => (
    <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2">
      <SceneChrome>
        <div className="h-full flex items-center justify-center text-ink-soft dark:text-moonlight text-sm">
          The route view (with the panel workspace underneath) renders here.
        </div>
      </SceneChrome>
    </div>
  ),
};

/** Honest stub — the "not yet" state, forced for visual regression. */
export const HonestStub: Story = {
  render: () => (
    <div className="h-screen bg-ice-2 dark:bg-space-2">
      <WorkflowStub workflow="write" forceUnbuiltForStory />
    </div>
  ),
};
