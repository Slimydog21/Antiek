import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";
import { within, userEvent, waitFor, expect } from "@storybook/test";

import SceneChrome from "./SceneChrome";
import { pendingForever, stubFetch } from "../modes/Reading/storyFetch";
import type { Thread } from "./threadModel";

/**
 * SceneChrome (SPR-04 zone 3) — the per-workflow scene wrapper: a contextual
 * ACTION BAR (the verbs the active workflow runs) + in-scene TABS (object
 * views) above the route view, with the SPR-06 cross-workflow thread
 * breadcrumb when an entity is in focus.
 *
 * ── Why this stories file exists (ALC SPR-09 product-character lift) ──────────
 * SceneChrome is a control-bearing shell surface — its action verbs carry a
 * disabled/busy state (the `run` verb guards double-clicks while it awaits a
 * create) and its tabs carry a rest/active(=current) pair. Before this file it
 * had NO co-located story, so its NON-DEFAULT states (busy action, active tab,
 * shared passthrough, with-thread) were never inspectable in isolation. Each
 * story below drives the REAL component into one state — nothing is faked.
 *
 * ── How the states are driven (honest, not mocked markup) ────────────────────
 * SceneChrome reads the active workflow from the ROUTE (`workflowForPath`), so
 * each story opts out of the global router (`parameters.router = false`) and
 * brings its own `<MemoryRouter initialEntries={[…]}>` pinned to the path that
 * selects the workflow being inspected. The busy/disabled state is the action
 * verb's real `run` await: the Write "New piece" verb calls `createDeliverable`
 * → `apiFetch` → `window.fetch`; `stubFetch(pendingForever)` pins that fetch
 * so the button's real reducer parks in its `Creating…`/`disabled` state for
 * inspection (the same lever the reading-mode stories use). The component's own
 * `setRunningAction` reducer runs — only the network is pinned.
 *
 * Werner skin (Lemon tokens) — no hardcoded colors; SPR-08 glass tokens
 * untouched.
 */
const meta = {
  title: "Shell / SceneChrome (SPR-04)",
  component: SceneChrome,
  parameters: { layout: "fullscreen" },
  // `a11y-audit` opts these stories into the test-runner axe gate
  // (.storybook/test-runner.ts, selected via `--includeTags a11y-audit`).
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof SceneChrome>;

export default meta;
type Story = StoryObj<typeof meta>;

function Body({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full flex items-center justify-center text-ink-soft dark:text-moonlight text-sm">
      {children}
    </div>
  );
}

/**
 * REST — Research scene chrome at `/`. The action bar shows Research's verbs
 * (New investigation [primary] · Ask · Outcomes) and the in-scene tabs
 * (Workstation / My research / Outcomes). At `/` the Workstation tab is the
 * CURRENT (active, sun-underlined) tab — the rest/active pair is visible in
 * one frame.
 */
export const ResearchRest: Story = {
  parameters: { router: false },
  render: () => {
    return (
      <MemoryRouter initialEntries={["/"]}>
        <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2">
          <SceneChrome>
            <Body>The route view + panel workspace renders here.</Body>
          </SceneChrome>
        </div>
      </MemoryRouter>
    );
  },
};

/**
 * ACTIVE TAB — the SAME Research chrome routed to `/outcomes`, so the Outcomes
 * tab is the current (active) crumb instead of Workstation. Pairs with
 * ResearchRest to show the tab's rest→active state differentiation as two
 * named stories, not one default render.
 */
export const ActiveOutcomesTab: Story = {
  parameters: { router: false },
  render: () => {
    return (
      <MemoryRouter initialEntries={["/outcomes"]}>
        <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2">
          <SceneChrome>
            <Body>Outcomes view — the Outcomes tab is the current crumb.</Body>
          </SceneChrome>
        </div>
      </MemoryRouter>
    );
  },
};

/**
 * WRITE REST — the Write scene at `/write`. Write declares a SINGLE primary
 * verb ("New piece") and NO tabs, so the chrome collapses to one action and no
 * tab row — the variant spread across workflows, authored as its own state.
 */
export const WriteRest: Story = {
  parameters: { router: false },
  render: () => {
    return (
      <MemoryRouter initialEntries={["/write"]}>
        <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2">
          <SceneChrome>
            <Body>The Write canvas renders here.</Body>
          </SceneChrome>
        </div>
      </MemoryRouter>
    );
  },
};

/**
 * BUSY / DISABLED — the Write "New piece" verb mid-create. The story stubs
 * `window.fetch` with `pendingForever` so the real `createDeliverable` await
 * never settles; the play function clicks the verb, driving the component's own
 * `runningAction` reducer into its busy state. The button shows `Creating…`,
 * is `disabled` + `aria-busy` — the rubric's sourced disabled state
 * (`disabled:opacity-60`), inspectable in isolation instead of flashing past.
 */
export const WriteActionCreating: Story = {
  parameters: { router: false },
  decorators: [stubFetch(pendingForever)],
  render: () => {
    return (
      <MemoryRouter initialEntries={["/write"]}>
        <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2">
          <SceneChrome>
            <Body>Creating a new piece — the verb is busy + disabled.</Body>
          </SceneChrome>
        </div>
      </MemoryRouter>
    );
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = await canvas.findByRole("button", { name: "New piece" });
    await userEvent.click(button);
    await waitFor(() => {
      const busy = canvas.getByRole("button", { name: "Creating…" });
      expect(busy).toBeDisabled();
      expect(busy).toHaveAttribute("aria-busy", "true");
    });
  },
};

const FLYWHEEL_THREAD: Thread = {
  canonicalEntityId: "insight-7f3a9c",
  canonicalEntityKind: "insight_node",
  isDegenerate: false,
  hops: [
    {
      workflow: "research",
      entityId: "insight-7f3a9c",
      entityKind: "insight_node",
      seamEventId: null,
      seamActionType: null,
      provenanceRef: null,
      built: true,
      viaProvisionalSeam: false,
    },
    {
      workflow: "read",
      entityId: "insight-7f3a9c",
      entityKind: "insight_node",
      seamEventId: "evt-r2read",
      seamActionType: "seam.research_to_read",
      provenanceRef: null,
      built: true,
      viaProvisionalSeam: false,
    },
  ],
  stubs: [],
};

/**
 * WITH THREAD — the chrome with an entity in focus, so the SPR-06
 * cross-workflow ThreadBreadcrumb row appears beneath the tabs. The
 * breadcrumb-present state is distinct from the (default) thread-absent state
 * the other stories show.
 */
export const WithThreadBreadcrumb: Story = {
  parameters: { router: false },
  render: () => {
    return (
      <MemoryRouter initialEntries={["/"]}>
        <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2">
          <SceneChrome thread={FLYWHEEL_THREAD} onThreadJump={() => {}}>
            <Body>An entity is in focus — its cross-workflow thread shows.</Body>
          </SceneChrome>
        </div>
      </MemoryRouter>
    );
  },
};

/**
 * SHARED PASSTHROUGH — a governance/operator route (here `/operator`). The
 * `wf === "shared"` branch renders children BARE: no action bar, no tabs. This
 * is the honest "no scene chrome here" state, authored so the passthrough is
 * inspectable rather than implicit.
 */
export const SharedPassthrough: Story = {
  parameters: { router: false },
  render: () => {
    return (
      <MemoryRouter initialEntries={["/operator"]}>
        <div className="h-screen flex flex-col bg-ice-2 dark:bg-space-2">
          <SceneChrome>
            <Body>
              Shared/operator surface — rendered bare, no workflow scene chrome.
            </Body>
          </SceneChrome>
        </div>
      </MemoryRouter>
    );
  },
};
