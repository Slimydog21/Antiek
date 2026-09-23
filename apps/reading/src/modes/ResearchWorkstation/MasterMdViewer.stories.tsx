import type { Meta, StoryObj } from "@storybook/react";

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

// The viewer renders a ParsedSynthesis (what parseSynthesis() derives from
// the event stream), not raw markdown; these fixtures were written against
// the older `markdown` prop, so the component received no synthesis at all.
const emptySynthesis: ParsedSynthesis = {
  synthesisId: null,
  thesisSummary: "",
  components: [],
  falsificationConditions: [],
  executionRisks: [],
  recommendation: "undetermined",
  hardConstraintsSatisfied: null,
  totalCostUsd: 0,
  question: null,
  masterMdPath: null,
  domainsPatched: [],
  chunkCitations: {},
  qualityScore: null,
  reuseProvenance: [],
  compoundingStat: null,
};

const sampleSynthesis: ParsedSynthesis = {
  ...emptySynthesis,
  synthesisId: "syn-storybook-demo",
  question: "Are neutral-atom gate error rates below threshold at the 100-qubit scale?",
  thesisSummary:
    "Neutral-atom platforms have published single-qubit gate error rates " +
    "clustering between 8×10⁻⁴ and 1.5×10⁻³ at the 100-qubit scale across " +
    "three independent groups in 2024-2025. Two of the three report errors " +
    "below the surface-code threshold.",
  components: [
    {
      index: 1,
      claim:
        "The Lukin lab and the QuEra production system both report errors " +
        "below the surface-code threshold.",
      rationale: "Two independent groups, the same gate decomposition.",
      confidence: "high",
      effectiveSourceTier: 1,
      hedgingRequired: false,
      chunkIds: ["chunk-lukin-2025", "chunk-quera-2025"],
      supportingPathIndices: [],
    },
    {
      index: 2,
      claim:
        "A circuit-depth normalization narrows the gap between groups by " +
        "roughly half an order of magnitude but does not eliminate it.",
      confidence: "moderate",
      effectiveSourceTier: 2,
      hedgingRequired: true,
      chunkIds: ["chunk-vuletic-2025"],
      supportingPathIndices: [],
    },
  ],
  falsificationConditions: [
    {
      condition:
        "A head-to-head benchmark with a shared gate decomposition shows the " +
        "gap is methodological.",
      specificObservable: "Error rates converge within 2×10⁻⁴ under one decomposition.",
    },
  ],
  executionRisks: [
    { risk: "No group has published a shared-decomposition benchmark yet." },
  ],
  recommendation: "conditional",
  totalCostUsd: 0.42,
  chunkCitations: {
    "chunk-lukin-2025": [1],
    "chunk-quera-2025": [1],
    "chunk-vuletic-2025": [2],
  },
};

export const SampleSynthesis: Story = {
  args: { synthesis: sampleSynthesis },
};

export const Empty: Story = {
  args: { synthesis: emptySynthesis },
};
