import type { Meta, StoryObj } from "@storybook/react";

import type { DistillationResponse, DistilledNode } from "../../lib/api";
import DistillView from "./DistillView";

const insight = (node_id: string, text: string, source = "source-demo"): DistilledNode => ({
  node_id,
  kind: "insight",
  text,
  confidence: "high",
  source_document_id: source,
  refinement_count: 0,
  escalated: false,
  reserved_child_investigation_id: null,
});

const question = (node_id: string, text: string, escalated = false): DistilledNode => ({
  node_id,
  kind: "question",
  text,
  confidence: null,
  source_document_id: "source-demo",
  refinement_count: 0,
  escalated,
  reserved_child_investigation_id: escalated ? "inv-reserved" : null,
});

const fixture: DistillationResponse = {
  investigation_id: "inv-field-ledger",
  insights: [
    insight("insight-1", "Independent benchmarks converge on a measurable latency advantage for small retrieval calls."),
    insight("insight-2", "The advantage disappears during long-context synthesis, where source reconciliation dominates runtime."),
    insight("insight-3", "Cost projections remain sensitive to cache-hit assumptions that none of the reports disclose."),
  ],
  questions: [
    question("question-1", "Which benchmark assumptions survive when provider-side caching is disabled?", true),
    question("question-2", "Can the same comparison be reproduced on the operator’s actual weekly task mix?"),
  ],
};

const meta = {
  title: "Loop 1 / Distillation field ledger",
  component: DistillView,
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <main className="min-h-screen bg-ice-2 p-4 dark:bg-space-2 sm:p-8">
        <h1 className="sr-only">Distillation field ledger</h1>
        <h2 className="sr-only">Research graph</h2>
        <div className="mx-auto max-w-[820px] border border-rule bg-ice-1 dark:border-charcoal-1 dark:bg-charcoal-2">
          <Story />
        </div>
      </main>
    ),
  ],
} satisfies Meta<typeof DistillView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const FiledAndUnresolved: Story = {
  args: {
    investigationId: fixture.investigation_id,
    showArtifactOutline: false,
    loadDistillation: async () => fixture,
    challengeInsight: async (nodeId) => ({
      node_id: nodeId,
      applied: false,
      superseded: true,
      escalated: false,
      reserved_child_investigation_id: null,
    }),
    onChase: () => undefined,
  },
};

export const NothingDistilled: Story = {
  args: {
    investigationId: "inv-empty",
    showArtifactOutline: false,
    loadDistillation: async () => ({ investigation_id: "inv-empty", insights: [], questions: [] }),
  },
};
