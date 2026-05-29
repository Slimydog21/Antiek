import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";

import AppShell from "./AppShell";
import { useWorkspace } from "./workspace/WorkspaceStore";

/**
 * AppShell — the full chrome. Renders:
 *   Topbar (top) · PanelLayout (left dock + main + right dock) · NavRail
 *   (BOTTOM, SPR-06).
 *
 * SPR-06 restructured the shell: the NavRail moved from the left to a
 * horizontal BOTTOM rail so the working region is full-width + symmetric
 * (the precondition for SPR-07's four-edge ad border). These stories are the
 * restructured-shell + bottom-nav acceptance surface — the bottom rail shows
 * the igloo home + four doors + More, and the main slot reaches edge-to-edge
 * above it with no left gutter.
 *
 * Two stories:
 *   - Empty       just chrome, no panels open. The main slot's
 *                 placeholder copy explains the next move.
 *   - WithProjectTree boots a ProjectTree panel docked-left so the
 *                 operator can see the full chrome (incl. a side dock living
 *                 INSIDE the full-width region) in action.
 */
const meta = {
  title: "Navigation / AppShell",
  component: AppShell,
  parameters: { layout: "fullscreen" },
  // `a11y-audit` opts this story into the test-runner axe gate
  // (.storybook/test-runner.ts, selected via `--includeTags a11y-audit`).
  // AppShell is the composed full-chrome story — auditing it covers the
  // NavRail + Topbar + SceneChrome chrome in one pass.
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof AppShell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  render: () => (
    <AppShell>
      <Placeholder />
    </AppShell>
  ),
};

export const WithProjectTree: Story = {
  render: () => {
    const Inner = () => {
      const open = useWorkspace((s) => s.open);
      const reset = useWorkspace((s) => s.reset);
      useEffect(() => {
        reset();
        open("ProjectTree", {}, {
          mode: "docked-left",
          title: "Project",
          id: "appshell:projecttree",
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);
      return (
        <AppShell>
          <Placeholder />
        </AppShell>
      );
    };
    return <Inner />;
  },
};

function Placeholder() {
  return (
    <div className="h-full w-full p-12 flex items-center justify-center">
      <div className="max-w-md text-center">
        <h1 className="text-2xl font-bold text-ink dark:text-bright mb-2">
          Main slot
        </h1>
        <p className="text-shadow-1 dark:text-moonlight text-sm leading-relaxed">
          The route's content renders here, full-width. Topbar (above) + NavRail
          (the bottom bar) + docked panels (sides) frame this content. Open
          panels persist as the operator navigates between routes (pin them to
          make them sticky).
        </p>
      </div>
    </div>
  );
}
