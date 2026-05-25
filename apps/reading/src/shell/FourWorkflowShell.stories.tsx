import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";
import {
  MemoryRouter,
  Routes,
  Route,
  useLocation,
} from "react-router-dom";

import { NavRail } from "../components/navigation/NavRail";
import { Topbar } from "../components/navigation/Topbar";
import { ProductsLauncher } from "../components/navigation/ProductsLauncher";
import ProjectTree from "../components/navigation/ProjectTree";
import { WorkflowStub } from "./WorkflowStub";
import { useActiveWorkflow } from "./activeWorkflow";
import { workflowForRoute } from "./workflowTaxonomy";

/**
 * FourWorkflowShell — the SPR-08 e2e target. Composes the four-workflow IA's
 * load-bearing pieces (NavRail · Topbar scene chrome · workflow-scoped
 * ProjectTree · ProductsLauncher) under one router with the four workflows'
 * home routes wired, so the e2e can walk the whole IA end-to-end:
 *
 *   - the rail carries exactly the four workflows
 *   - clicking a workflow re-scopes the ProjectTree (reads useActiveWorkflow)
 *     AND re-renders the Topbar scene chrome (derived from workflowForRoute)
 *   - a built tab is a live NavLink; a soon tab is a disabled affordance
 *   - the products launcher lists every mode
 *
 * Why a constituent-composition story, not the live <App />: the live app
 * gates on auth (RequireAuth → /login without api.antiek.ai), so a headless
 * live-app e2e isn't runnable in this environment. The established pattern is
 * to drive a Storybook story (see e2e/{operator-day,smoke}.spec.ts), so this
 * story composes the real shell components — not mocks — under a MemoryRouter.
 * It is NOT the live routed App; it asserts the IA wiring, not auth/data.
 *
 * The route→activeWorkflow sync mirrors AppShell.tsx so a deep route or a rail
 * click keeps the tree scoped to the same workflow the chrome shows.
 */
const meta = {
  title: "Navigation / FourWorkflowShell",
  // `router: false` — this story owns its MemoryRouter (it wires the four
  // workflows' routes for the walk), so the global decorator steps aside.
  parameters: { layout: "fullscreen", router: false },
  tags: ["a11y-audit"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/** Mirror AppShell's route→activeWorkflow sync so the tree follows navigation. */
function WorkflowSync() {
  const { pathname } = useLocation();
  const setActive = useActiveWorkflow((s) => s.set);
  useEffect(() => {
    const w = workflowForRoute(pathname);
    if (w) setActive(w);
  }, [pathname, setActive]);
  return null;
}

/** A thin body that names the current route + workflow so the e2e can assert
 *  the scene body changed when navigating. The real app route-renders the mode
 *  here; the story keeps it a label so the chrome + tree stay the subject. */
function SceneBody() {
  const { pathname } = useLocation();
  const w = workflowForRoute(pathname);
  return (
    <div
      data-testid="scene-body"
      data-workflow={w ?? "shared"}
      className="flex-1 min-h-0 overflow-auto p-8 font-mono text-[12px] text-shadow-1 dark:text-moonlight bg-ice-2 dark:bg-space-2"
    >
      <p>
        route:{" "}
        <span className="text-ink dark:text-bright" data-testid="scene-route">
          {pathname}
        </span>
      </p>
      <p>
        workflow:{" "}
        <span className="text-ink dark:text-bright">{w ?? "shared"}</span>
      </p>
    </div>
  );
}

/** A soon-tab surface mounted under a dedicated route so the e2e can navigate
 *  to it and assert the honest stub renders. */
function StubRoute() {
  return (
    <div
      data-testid="scene-body"
      className="flex-1 min-h-0 overflow-auto bg-ice-2 dark:bg-space-2"
    >
      <WorkflowStub label="Trajectory" />
    </div>
  );
}

function Shell() {
  return (
    <div className="h-screen w-screen flex bg-ice-2 dark:bg-space-2 text-ink dark:text-bright overflow-hidden">
      <WorkflowSync />
      <NavRail />
      <div className="flex-1 min-w-0 flex flex-col">
        <Topbar />
        <div className="flex-1 min-h-0 flex">
          {/* The persistent content column — workflow-scoped tree. */}
          <aside
            aria-label="Content tree"
            className="w-[300px] shrink-0 h-full overflow-y-auto border-r border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2"
          >
            <ProjectTree />
          </aside>
          {/* The scene body — route-rendered (label stand-in for the mode). */}
          <Routes>
            {/* the one soon-tab route the e2e walks to assert the stub */}
            <Route path="/research/trajectory" element={<StubRoute />} />
            <Route path="*" element={<SceneBody />} />
          </Routes>
        </div>
      </div>
      <ProductsLauncher />
    </div>
  );
}

/**
 * The default walk story: starts at Research home. The e2e drives the rail to
 * each workflow and asserts the tree + chrome re-scope.
 */
export const Walk: Story = {
  render: () => (
    <MemoryRouter initialEntries={["/"]}>
      <Shell />
    </MemoryRouter>
  ),
};
