import type { Meta, StoryObj } from "@storybook/react";

import {
  mockDecomposeDeliveredEvent,
  mockDispatchCallEvent,
  mockEvidenceDeliveredEvent,
  mockPhaseEnterEvent,
  mockSynthesizeDeliveredEvent,
} from "../../components/__fixtures__";
import PhaseRow from "./PhaseRow";

/**
 * PhaseRow renders one trajectory event. Variant-based on action_type.
 * Stories cover the headline variants: decompose, evidence, synthesize,
 * dispatch, plus the suppressed phase.enter (renders nothing).
 */
const meta = {
  title: "Loop 1 / PhaseRow",
  component: PhaseRow,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof PhaseRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Decompose: Story = {
  args: { event: mockDecomposeDeliveredEvent },
};

export const Evidence: Story = {
  args: { event: mockEvidenceDeliveredEvent },
};

export const Synthesize: Story = {
  args: { event: mockSynthesizeDeliveredEvent },
};

export const Dispatch: Story = {
  args: { event: mockDispatchCallEvent },
};

export const PhaseEnterSuppressed: Story = {
  args: { event: mockPhaseEnterEvent },
};
