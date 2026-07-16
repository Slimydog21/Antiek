import type { Meta, StoryObj } from "@storybook/react";
import Settings from "./index";

const meta = {
  title: "Settings/Model Observatory",
  component: Settings,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof Settings>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Production: Story = {};
export const Wide: Story = { parameters: { viewport: { defaultViewport: "desktop" } } };
export const Tablet: Story = { parameters: { viewport: { defaultViewport: "tablet" } } };
export const Mobile: Story = { parameters: { viewport: { defaultViewport: "mobile1" } } };
