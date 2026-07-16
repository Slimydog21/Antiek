import type { Meta, StoryObj } from "@storybook/react";

import Biography from "./index";

const composition = {
  investigationId: "inv-memory-archive",
  deliverableId: "deliverable-memory-archive",
  projectId: "speak-memory-archive",
};

const meta = {
  title: "Loop 1 / Biography Memory Archive",
  component: Biography,
  parameters: { layout: "fullscreen" },
  tags: ["a11y-audit"],
} satisfies Meta<typeof Biography>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Landing: Story = {
  args: { executionEnabled: false },
};

export const Preparing: Story = {
  args: {
    executionEnabled: false,
    initialSubjectName: "Maria Alvarez",
    initialSubmitting: true,
  },
};

export const ResearchSafeCompositionFailed: Story = {
  args: {
    executionEnabled: false,
    initialSubjectName: "Maria Alvarez",
    initialInvestigationId: composition.investigationId,
    initialFailed: true,
  },
};

export const StartFailed: Story = {
  args: {
    executionEnabled: false,
    initialSubjectName: "Maria Alvarez",
    initialFailed: true,
  },
};

export const Composed: Story = {
  args: {
    executionEnabled: false,
    initialSubjectName: "Maria Alvarez",
    initialComposition: composition,
  },
};

export const CreatingInviteLink: Story = {
  args: {
    ...Composed.args,
    initialInviting: true,
  },
};

export const InviteLinkFailed: Story = {
  args: {
    ...Composed.args,
    initialInviteFailed: true,
  },
};

export const InviteLinkReady: Story = {
  args: {
    ...Composed.args,
    initialInviteLink: "https://antiek.example/speak/invite/example-token",
  },
};

export const Night: Story = {
  args: Composed.args,
  decorators: [(Story) => <div className="biography-memory-archive--night bg-space-2"><Story /></div>],
};

export const Narrow: Story = {
  args: InviteLinkReady.args,
  parameters: { viewport: { defaultViewport: "mobile1" } },
  decorators: [(Story) => <div style={{ width: 375, height: 667, overflow: "hidden" }}><Story /></div>],
};
