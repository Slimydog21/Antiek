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

const sampleSynthesis = {
  synthesisId: null,
  thesisSummary:
    "Published neutral-atom gate error rates cluster near the threshold for fault-tolerant operation, but the reported gates and measurement methods differ.",
  components: [
    {
      index: 1,
      claim:
        "A shared gate decomposition is needed before the reported error rates can be compared directly.",
      confidence: "high",
      effectiveSourceTier: 2,
      hedgingRequired: false,
      chunkIds: [],
      supportingPathIndices: [],
    },
  ],
  falsificationConditions: [],
  executionRisks: [],
  recommendation: "conditional",
  hardConstraintsSatisfied: null,
  totalCostUsd: 0,
  question: "How do neutral-atom gate error rates compare at the 100-qubit scale?",
  masterMdPath: null,
  domainsPatched: [],
  chunkCitations: {},
  qualityScore: null,
  reuseProvenance: [],
  compoundingStat: null,
} satisfies ParsedSynthesis;

const emptySynthesis = {
  ...sampleSynthesis,
  thesisSummary: "",
  components: [],
  recommendation: "undetermined",
  question: null,
} satisfies ParsedSynthesis;

export const SampleSynthesis: Story = {
  args: {
    synthesis: sampleSynthesis,
  },
};

export const Empty: Story = {
  args: {
    synthesis: emptySynthesis,
  },
};
