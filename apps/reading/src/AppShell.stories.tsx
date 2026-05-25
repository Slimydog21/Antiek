import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";

import AppShell from "./AppShell";
import { useWorkspace } from "./workspace/WorkspaceStore";

/**
 * AppShell — the S4 acceptance gate. Renders the full chrome:
 *   NavRail · Topbar · PanelLayout (left dock + main + right dock)
 *
 * Two stories:
 *   - Empty       just chrome, no panels open. The main slot's
 *                 placeholder copy explains the next move.
 *   - WithProjectTree boots a ProjectTree panel docked-left so the
 *                 operator can see the full S4 chrome in action.
 */
const meta = {
  title: "Navigation / AppShell",
  component: AppShell,
  parameters: { layout: "fullscreen" },
  // `a11y-audit` opts this story into the test-runner axe gate.
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
          The route's content renders here. NavRail (left) + Topbar (above) +
          docked panels (sides) frame this content. Open panels persist as the
          operator navigates between routes (pin them to make them sticky).
        </p>
      </div>
    </div>
  );
}
