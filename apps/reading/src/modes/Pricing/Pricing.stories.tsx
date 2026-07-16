import type { Meta, StoryObj } from "@storybook/react";
import { ExpeditionCostPlanner } from "./index";

const meta = {
  title: "Modes/Expedition Cost Planner",
  component: ExpeditionCostPlanner,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof ExpeditionCostPlanner>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Production: Story = {};
export const VisualFixture: Story = { args: { visualFixture: true } };
export const CapCrossing: Story = {
  args: {
    initialPrivateTokens: 2_000_000,
    initialPublicTokens: 8_000_000,
    initialRatePerMillion: 8.5,
  },
};
export const Night: Story = {
  args: {
    initialPrivateTokens: 4_000_000,
    initialPublicTokens: 12_000_000,
    initialRatePerMillion: 14,
  },
};
export const Narrow: Story = {
  args: {
    initialPrivateTokens: 50_000_000,
    initialPublicTokens: 50_000_000,
    initialRatePerMillion: 100,
  },
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
