/**
 * MyResearch.stories.tsx — deterministic Storybook story for the research
 * lineage board (MyResearch family/cascade tree view).
 *
 * The fixture seam is the `investigations` array passed to the exported
 * `ResearchLineageBoard` component. The story bypasses all hooks
 * (useInvestigationList, useAuth, getBudgetDefaults) by rendering the
 * pure board component directly — an honest seam that proves the tree
 * hierarchy without mocking production data-fetching.
 *
 * No generated art, no MSW layer, no dependencies beyond Storybook +
 * React Router (provided by the global preview decorator).
 */
import type { Meta, StoryObj } from "@storybook/react";

import { ResearchLineageBoard } from "./MyResearch";
import type { InvestigationSummary } from "../../lib/api";

// ── Deterministic fixture ─────────────────────────────────────────────
//
// Every field is a literal — no Date.now(), no Math.random(), no network.
// The fixture covers:
//   • A 3-generation family (root → child → grandchild)
//   • Mixed statuses (completed, in_progress, failed)
//   • A daemon-spawned child ("found by the loop")
//   • A standalone research (no parent, no children)
//   • Realistic but fixed costs and timestamps

const FIXTURE: InvestigationSummary[] = [
  {
    investigation_id: "inv-root-001",
    question: "What are the economic effects of deep-sea mining on Pacific Island nations?",
    status: "completed",
    started_at: "2026-07-10T09:00:00Z",
    completed_at: "2026-07-10T09:45:00Z",
    cost_usd_total: 0.1234,
    parent_investigation_id: null,
  },
  {
    investigation_id: "inv-child-001",
    question: "How does deep-sea mining affect tuna fisheries in the EEZ?",
    status: "in_progress",
    started_at: "2026-07-10T09:50:00Z",
    completed_at: null,
    cost_usd_total: 0.0456,
    parent_investigation_id: "inv-root-001",
    spawned_by_daemon: true,
  },
  {
    investigation_id: "inv-child-002",
    question: "What compensation frameworks exist for seabed resource extraction?",
    status: "completed",
    started_at: "2026-07-10T09:52:00Z",
    completed_at: "2026-07-10T10:30:00Z",
    cost_usd_total: 0.0789,
    parent_investigation_id: "inv-root-001",
  },
  {
    investigation_id: "inv-grandchild-001",
    question: "Has the ISA issued any provisional licenses in the Clarion-Clipperton Zone since 2024?",
    status: "failed",
    started_at: "2026-07-10T10:00:00Z",
    completed_at: null,
    cost_usd_total: 0.0111,
    parent_investigation_id: "inv-child-002",
  },
  {
    investigation_id: "inv-standalone-001",
    question: "What is the current state of mRNA vaccine patents globally?",
    status: "completed",
    started_at: "2026-07-09T14:00:00Z",
    completed_at: "2026-07-09T14:30:00Z",
    cost_usd_total: 0.0320,
    parent_investigation_id: null,
  },
];

const FIXED_NOW_MS = Date.parse("2026-07-15T12:00:00Z");

const meta = {
  title: "ResearchWorkstation / MyResearch / LineageBoard",
  component: ResearchLineageBoard,
  parameters: {
    layout: "fullscreen",
    // The global preview decorator wraps in MemoryRouter; the board
    // component uses <Link> which needs a router context.
  },
  decorators: [
    (Story) => (
      <main className="min-h-screen bg-ice-0 p-4 text-ink dark:bg-charcoal-2 dark:text-bright md:p-8">
        <h1 className="sr-only">Research lineage board</h1>
        <div className="mx-auto max-w-5xl">
          <Story />
        </div>
      </main>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof ResearchLineageBoard>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Full lineage board — shows a family tree with root, children, and a
 * grandchild, plus a standalone research. The tree connectors (trunk +
 * branch arms) are CSS-only pseudo-elements on the marker divs.
 */
export const FullLineage: Story = {
  args: {
    investigations: FIXTURE,
    nowMs: FIXED_NOW_MS,
  },
};

/**
 * Standalone only — no families, no tree. Verifies the flat card
 * rendering when every research has no parent and no children.
 */
export const StandaloneOnly: Story = {
  args: {
    investigations: [
      {
        investigation_id: "inv-solo-001",
        question: "What are the health effects of intermittent fasting?",
        status: "completed",
        started_at: "2026-07-10T12:00:00Z",
        completed_at: "2026-07-10T12:20:00Z",
        cost_usd_total: 0.0150,
        parent_investigation_id: null,
      },
      {
        investigation_id: "inv-solo-002",
        question: "How does urbanisation affect pollinator diversity?",
        status: "in_progress",
        started_at: "2026-07-10T13:00:00Z",
        completed_at: null,
        cost_usd_total: 0.0080,
        parent_investigation_id: null,
      },
    ],
    nowMs: FIXED_NOW_MS,
  },
};

/**
 * Empty state — the board returns null when the list is empty.
 * Storybook will show a blank canvas; this is the honest "nothing to
 * render" state.
 */
export const Empty: Story = {
  args: {
    investigations: [],
    nowMs: FIXED_NOW_MS,
  },
};
