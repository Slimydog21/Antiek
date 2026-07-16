import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import { mockEventStream } from "../../components/__fixtures__";
import Replay from "./index";

const events = mockEventStream.slice(0, 6);
const meta = {
  title: "Research / Investigation Replay Observatory",
  component: Replay,
  render: (args) => <MemoryRouter><Replay {...args} executionEnabled={false} /></MemoryRouter>,
  args: { investigationId: "inv-polaris", initialEvents: events },
  parameters: { layout: "fullscreen" },
  argTypes: { executionEnabled: { control: false, table: { disable: true } } },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof Replay>;

export default meta;
type Story = StoryObj<typeof meta>;

export const RecordedTrail: Story = {};
export const LiveTail: Story = { args: { initialConnected: true } };
export const WaitingForEvents: Story = { args: { initialEvents: [] } };
export const LoadingHistory: Story = { args: { initialEvents: [], initialLoading: true } };
export const SafeFailure: Story = { args: { initialEvents: [], initialError: true } };
export const NightWatch: Story = {
  render: (args) => <MemoryRouter><div className="dark"><Replay {...args} executionEnabled={false} /></div></MemoryRouter>,
  parameters: { backgrounds: { default: "dark" } },
};
export const NarrowInstrument: Story = { parameters: { viewport: { defaultViewport: "tablet" } } };
