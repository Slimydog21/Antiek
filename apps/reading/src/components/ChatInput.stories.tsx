import type { Meta, StoryObj } from "@storybook/react";

import ChatInput from "./ChatInput";

/**
 * ChatInput is the wrestling-mode chat affordance: textarea + Ask
 * button + region-context chip showing the highlighted PDF excerpt.
 * Posts a distillation.requested event scoped to the last selected
 * region. See master-spec §4.2 (Surface B — Document Wrestle).
 *
 * Voice/style discipline (§5.5): serif typography on white, no
 * forced bullets, claim spans inline.
 */
const meta = {
  title: "Loop 2 / ChatInput",
  component: ChatInput,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ChatInput>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WholeDocumentScope: Story = {
  args: {
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
    region: null,
    disabled: false,
  },
};

export const RegionScoped: Story = {
  args: {
    investigationId: "inv-storybook-demo",
    documentId: "doc-quantum-2026",
    region: {
      region_id: "reg-abc123",
      page: 4,
      text_excerpt:
        "Neutral-atom platforms have demonstrated error rates below 10⁻³ at 100-qubit scale.",
    },
    disabled: false,
  },
};

export const DisabledNoDocument: Story = {
  args: {
    investigationId: "inv-storybook-demo",
    documentId: null,
    region: null,
    disabled: true,
  },
};
