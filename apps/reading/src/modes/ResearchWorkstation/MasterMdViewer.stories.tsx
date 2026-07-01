import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import type { ParsedSynthesis } from "../../lib/synthesisParser";
import MasterMdViewer from "./MasterMdViewer";

/**
 * MasterMdViewer is the operator-facing synthesis renderer. Master-spec
 * §2.4 (synthesis as the human-facing artifact) + §5 voice and style
 * discipline (the prose that lands here MUST be slop-free).
 *
 * Sprint 17 included for design-system documentation; the Sprint 18-19
 * Wedge 2 notebook surface (master §4.2) extends the MASTER.md viewer
 * with literate-analysis blocks (region embeds, claim cards, LaTeX).
 */
const meta = {
  title: "Loop 1 / MasterMdViewer",
  component: MasterMdViewer,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof MasterMdViewer>;

export default meta;
type Story = StoryObj<typeof meta>;

const sampleSynthesis = `# Neutral-atom error rates at 100-qubit scale — synthesis

## Insights

Neutral-atom platforms have published single-qubit gate error rates
clustering between 8×10⁻⁴ and 1.5×10⁻³ at the 100-qubit scale across
three independent groups in 2024-2025. The Lukin lab and the QuEra
production system both report errors below the surface-code
threshold; the Vuletic preprint reports values above threshold using
a different gate decomposition.

The cross-comparison is not trivial because the gate-set choices
affect the effective error rate. A circuit-depth normalization
narrows the gap between groups by roughly half an order of
magnitude but does not eliminate it.

## Open questions

The remaining question worth chasing: is the gap between groups a
genuine difference in platform physics or an artifact of measurement
methodology? Resolving it requires a head-to-head benchmark with a
shared gate decomposition, which no group has yet published.
`;

export const SampleSynthesis: Story = {
  args: {
    markdown: sampleSynthesis,
    investigationId: "inv-storybook-demo",
  },
};

export const Empty: Story = {
  args: {
    markdown: "",
    investigationId: "inv-storybook-demo",
  },
};

const reuseSynthesis: ParsedSynthesis = {
  thesisSummary: "Prior retrieval narrowed the question before this run started.",
  components: [
    {
      index: 1,
      claim: "The new answer reuses two prior insights without claiming a cold-baseline measurement.",
      confidence: "high",
      effectiveSourceTier: 2,
      hedgingRequired: false,
      chunkIds: [],
      supportingPathIndices: [],
    },
  ],
  falsificationConditions: [],
  executionRisks: [],
  recommendation: "proceed",
  hardConstraintsSatisfied: true,
  totalCostUsd: 0.04,
  question: "What did this investigation build on?",
  masterMdPath: null,
  domainsPatched: [],
  chunkCitations: {},
  qualityScore: null,
  reuseProvenance: [
    { unitId: "ku-neutral-atom-gate-errors", sourceInvestigationId: "inv-prior-1", score: 0.91 },
    { unitId: "ku-circuit-depth-normalisation", sourceInvestigationId: "inv-prior-2", score: 0.84 },
  ],
  compoundingStat: null,
};

export const ReuseProvenance: Story = {
  tags: ["a11y-audit"],
  render: () => (
    <MemoryRouter>
      <div className="max-w-3xl">
        <MasterMdViewer
          synthesis={reuseSynthesis}
          investigationId="inv-storybook-reuse"
          synthesisId="syn-storybook-reuse"
        />
      </div>
    </MemoryRouter>
  ),
};
