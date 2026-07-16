import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import CrossGraphCitations from "./index";
import type { RecordedCitation } from "./index";

const receipt: RecordedCitation = {
  reference_id: "ref_story_01",
  referencing_user_id: "__operator__",
  referencing_investigation_id: "inv-atlas",
  referenced_user_id: "research-partner",
  referenced_note_id: "note-fieldwork",
  federated_substrate_id: null,
  cited_at: "2026-07-16T12:00:00Z",
};
const inertRecord = async () => receipt;

const meta = {
  title: "Cross graph / Citation Attribution Switchyard",
  component: CrossGraphCitations,
  render: (args) => <MemoryRouter><CrossGraphCitations {...args} recordCitation={inertRecord} executionEnabled={false} /></MemoryRouter>,
  parameters: { layout: "fullscreen" },
  argTypes: { executionEnabled: { control: false, table: { disable: true } }, recordCitation: { control: false, table: { disable: true } } },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof CrossGraphCitations>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Ready: Story = {};
export const Federation: Story = { args: { initialFederation: true } };
export const Submitting: Story = { args: { initialFederation: true, submittingPreview: true } };
export const SafeFailure: Story = {
  render: (args) => <MemoryRouter><CrossGraphCitations {...args} recordCitation={async () => { throw new Error("secret upstream body"); }} /></MemoryRouter>,
  args: { initialFederation: true },
  play: async ({ canvasElement }) => {
    const button = canvasElement.querySelector<HTMLButtonElement>("button");
    button?.click();
  },
};
export const Recorded: Story = { args: { initialRecorded: [receipt] } };
export const Night: Story = { args: { initialRecorded: [receipt] }, parameters: { backgrounds: { default: "dark" } } };
export const Narrow: Story = { args: { initialFederation: true }, parameters: { viewport: { defaultViewport: "mobile1" } } };
