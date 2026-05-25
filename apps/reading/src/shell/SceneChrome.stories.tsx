import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import { Topbar } from "../components/navigation/Topbar";
import { WorkflowStub } from "./WorkflowStub";
import { SCENE_REGISTRY } from "./sceneRegistry";

/**
 * Scene chrome (SPR-05) — the Topbar hosting the per-workflow action bar +
 * in-scene tab strip. Each story mounts the Topbar at a representative route
 * so the chrome resolves through `workflowForRoute` exactly as in the app.
 *
 * The four workflow stories show each descriptor's verbs + tabs (with `soon`
 * tabs rendered as honest disabled affordances). The shared-route story shows
 * the chrome dropping out entirely — the Topbar renders bare. The stub story
 * shows what a `soon` tab's surface looks like when reached.
 *
 * These stories render the Topbar in isolation (no PanelLayout) so the chrome
 * itself is the subject; AppShell.stories already covers the composed shell.
 */
const meta = {
  title: "Navigation / SceneChrome",
  component: Topbar,
  // `router: false` — each story owns its MemoryRouter (mounted at a fixed
  // route so workflowForRoute resolves the right chrome), so the global router
  // steps aside instead of nesting (a nested router renders the SB error
  // screen — the bug SPR-08 caught + fixed).
  parameters: { layout: "fullscreen", router: false },
  // `a11y-audit` opts these stories into the test-runner axe gate
  // (.storybook/test-runner.ts, selected via `--includeTags a11y-audit`).
  tags: ["a11y-audit"],
} satisfies Meta<typeof Topbar>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Mount the Topbar at a fixed route. Routes are declared so NavLink active
 *  state resolves; the body is a thin label so the chrome stays the subject. */
function ChromeAt({ path }: { path: string }) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2">
        <Topbar />
        <div className="flex-1 p-8 font-mono text-[12px] text-shadow-1 dark:text-moonlight">
          route: <span className="text-ink dark:text-bright">{path}</span>
          <Routes>
            <Route path="*" element={null} />
          </Routes>
        </div>
      </div>
    </MemoryRouter>
  );
}

export const Research: Story = { render: () => <ChromeAt path="/" /> };
export const Read: Story = { render: () => <ChromeAt path="/documents" /> };
export const Write: Story = { render: () => <ChromeAt path="/create" /> };
export const Speak: Story = { render: () => <ChromeAt path="/interviews" /> };

/** Shared/operator route — the chrome drops out; the Topbar is bare. */
export const SharedRouteBare: Story = { render: () => <ChromeAt path="/billing" /> };

/** A `soon` tab's surface: the honest WorkflowStub naming its owning sprint. */
export const SoonTabStub: Story = {
  render: () => {
    const soon = SCENE_REGISTRY.read.tabs.find((t) => t.builtState === "soon")!;
    return (
      <MemoryRouter>
        <div className="h-screen bg-ice-2 dark:bg-space-2">
          <WorkflowStub label={soon.label} />
        </div>
      </MemoryRouter>
    );
  },
};
