import type { Meta, StoryObj } from "@storybook/react";

import type { Claim } from "../generated/types";
import ClaimCard from "./ClaimCard";

/**
 * ClaimCard renders a single Claim with confidence badge, attribution
 * region chips, challenge button, and (when grounded) the
 * GroundingBadge with passed/failed/pending status. Master-spec §2.1
 * insight/question structure.
 *
 * The four confidence levels (high/moderate/low/unknown) map to the
 * four-color badge palette per master-spec §5.5 visual discipline.
 */
const meta = {
  title: "Loop 2 / ClaimCard",
  component: ClaimCard,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ClaimCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const baseClaim: Claim = {
  claim_id: "cl-storybook-1",
  claim_text:
    "Neutral-atom platforms have demonstrated single-qubit gate error " +
    "rates below 10⁻³ at the 100-qubit scale, consistent with the " +
    "threshold thesis for fault-tolerant operation.",
  confidence: "high",
  attribution_region_ids: ["reg-abc123", "reg-def456"],
};

export const HighConfidence: Story = {
  args: {
    claim: baseClaim,
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
  },
};

export const ModerateConfidence: Story = {
  args: {
    claim: { ...baseClaim, confidence: "moderate" },
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
  },
};

export const LowConfidence: Story = {
  args: {
    claim: { ...baseClaim, confidence: "low" },
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
  },
};

export const WithPassedGrounding: Story = {
  args: {
    claim: baseClaim,
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
    grounding: {
      status: "passed",
      located_region_id: "reg-abc123",
      confidence: 0.92,
    },
  },
};

export const WithFailedGrounding: Story = {
  args: {
    claim: baseClaim,
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
    grounding: {
      status: "failed",
      reason: "absent_from_source",
      searched_region_count: 5,
    },
  },
};

export const PendingGrounding: Story = {
  args: {
    claim: baseClaim,
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
    grounding: { status: "pending" },
  },
};
