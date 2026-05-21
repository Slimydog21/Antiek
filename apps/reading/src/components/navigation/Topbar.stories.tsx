import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import Topbar from "./Topbar";

/**
 * Topbar with route-derived breadcrumbs. Wrap each story in its own
 * MemoryRouter so the breadcrumb output reflects the URL path.
 */
const meta = {
  title: "Navigation / Topbar",
  component: Topbar,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof Topbar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Research: Story = {
  render: () => (
    <MemoryRouter initialEntries={["/"]}>
      <div className="bg-ice-2 dark:bg-space-2 min-h-[80vh]">
        <Topbar />
      </div>
    </MemoryRouter>
  ),
};

export const Investigation: Story = {
  render: () => (
    <MemoryRouter initialEntries={["/inv/nvda-q4"]}>
      <div className="bg-ice-2 dark:bg-space-2 min-h-[80vh]">
        <Topbar />
      </div>
    </MemoryRouter>
  ),
};

export const DeepRoute: Story = {
  render: () => (
    <MemoryRouter initialEntries={["/cross-graph/citations"]}>
      <div className="bg-ice-2 dark:bg-space-2 min-h-[80vh]">
        <Topbar />
      </div>
    </MemoryRouter>
  ),
};
