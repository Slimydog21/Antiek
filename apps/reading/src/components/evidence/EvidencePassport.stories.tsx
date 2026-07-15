import type { Meta, StoryObj } from "@storybook/react";

import EvidencePassport from "./EvidencePassport";

const meta = {
  title: "Evidence / Source passport (ESP-01)",
  component: EvidencePassport,
  parameters: { layout: "centered" },
  tags: ["autodocs", "a11y-audit"],
  decorators: [
    (Story) => (
      <div className="w-[min(34rem,calc(100vw-2rem))] p-4">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof EvidencePassport>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AnchorPending: Story = {
  args: {
    sourceName: "The Timeless Way of Building",
    locator: "Page 12",
    custody: "source-identified",
    precision: "anchor-pending",
  },
};

export const ExactPassage: Story = {
  args: {
    sourceName: "A Pattern Language",
    locator: "Page 18 · passage 4",
    custody: "source-identified",
    precision: "exact-passage",
  },
};

export const HashReviewed: Story = {
  args: {
    sourceName: "Research on organizational memory",
    locator: "Research 2 of 3",
    custody: "hash-reviewed",
    precision: "artifact-snapshot",
  },
};

export const Restricted: Story = {
  args: {
    sourceName: "Licensed source",
    custody: "restricted",
    precision: "document-only",
  },
};

export const RightsUnconfirmed: Story = {
  args: {
    sourceName: "Known document",
    custody: "rights-unconfirmed",
    precision: "document-only",
  },
};

export const Unavailable: Story = {
  args: {
    sourceName: null,
    custody: "unavailable",
    precision: "no-anchor",
  },
};

export const ComposeSpine: Story = {
  args: {
    sourceName: "Research on organizational memory",
    locator: "Research 1 of 2",
    custody: "hash-reviewed",
    precision: "artifact-snapshot",
  },
  render: () => (
    <ol className="w-full space-y-2" aria-label="Source spine carried into Write">
      <li>
        <EvidencePassport
          sourceName="Research on organizational memory"
          locator="Research 1 of 2"
          custody="hash-reviewed"
          precision="artifact-snapshot"
        />
      </li>
      <li>
        <EvidencePassport
          sourceName="How research teams preserve dissent"
          locator="Research 2 of 2"
          custody="hash-reviewed"
          precision="artifact-snapshot"
        />
      </li>
    </ol>
  ),
};
