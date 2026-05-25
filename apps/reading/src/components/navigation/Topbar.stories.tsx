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
  // `router: false` — these stories own their MemoryRouter (each mounts at a
  // specific route for breadcrumb output), so the global router steps aside
  // instead of nesting (a nested router renders the SB error screen).
  parameters: { layout: "fullscreen", router: false },
  // `a11y-audit` opts this story into the test-runner axe gate.
  tags: ["autodocs", "a11y-audit"],
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
