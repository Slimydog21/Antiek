import type { Meta, StoryObj } from "@storybook/react";

import { IglooDirectory } from "./index";

const meta = {
  title: "Modes / Igloo Directory",
  component: IglooDirectory,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof IglooDirectory>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Production: Story = {};

export const VisualFixture: Story = { args: { visualFixture: true } };

export const Night: Story = {
  parameters: { backgrounds: { default: "space-2 (night)" } },
};

export const Narrow: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
