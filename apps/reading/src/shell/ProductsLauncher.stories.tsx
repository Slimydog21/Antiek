import type { Meta, StoryObj } from "@storybook/react";

import { ProductsLauncher } from "./ProductsLauncher";

/**
 * ProductsLauncher (SPR-04 zone-1 ⊞) — the honest full surface inventory of
 * EVERY mode. Two calm top-level groups (workflow deep modes under their
 * workflows; run & settings for Operator/Trust/Settings/governance) with
 * human labels. The pressure-release valve that keeps the rail at exactly
 * four workflows: everything else lives here + in ⌘K.
 *
 * In the app, NavRail owns the open state and renders this as a controlled
 * component (`<ProductsLauncher open={launcherOpen} onClose={…} />`). The story
 * mounts it `open` directly so the full inventory is the subject.
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
