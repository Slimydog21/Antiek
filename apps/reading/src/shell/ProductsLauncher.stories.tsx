import type { Meta, StoryObj } from "@storybook/react";

import { ProductsLauncher } from "./ProductsLauncher";

/**
 * ProductsLauncher (SPR-04 zone-1 ⊞) — the honest full surface inventory of
 * EVERY mode, grouped by workflow + a shared/operator section, with each
 * mode's build status shown truthfully. It is the pressure-release valve that
 * lets the rail stay at four workflows: the deep modes live here + in ⌘K,
 * never on the rail.
 *
 * In the app, NavRail owns the open state and renders this as a controlled
 * component (`<ProductsLauncher open={launcherOpen} onClose={…} />`). The story
 * mounts it `open` directly so the full inventory is the subject.
 *
 * Harvested from PR #8 (caffen/SPR-08) and re-pointed from the deleted
 * `components/navigation/ProductsLauncher` (which self-managed via a window
 * event) to the unified `src/shell/ProductsLauncher` (controlled props).
 */
const meta = {
  title: "Shell / ProductsLauncher",
  component: ProductsLauncher,
  parameters: { layout: "fullscreen" },
  // `a11y-audit` opts this story into the test-runner axe gate. The launcher
  // is shippable UI — the audit covers it like any other surface.
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof ProductsLauncher>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The launcher open over the full inventory. */
export const Open: Story = {
  args: {
    open: true,
    onClose: () => {},
  },
  render: (args) => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">
      <ProductsLauncher {...args} />
    </div>
  ),
};
