import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";

import { ProductsLauncher } from "./ProductsLauncher";

/**
 * ProductsLauncher — the full surface inventory grouped + demoted off the
 * rail. The four workflows sit in the surfaced "Workspaces" group; the ~31
 * other modes are grouped below. Opened from the rail's ⊞ button via the
 * `antiek:launcher:toggle` window event.
 *
 * The launcher renders nothing until that event fires, so the story dispatches
 * it on mount (the same event the rail button dispatches) — no private API,
 * the story drives the real open path.
 *
 * `a11y-audit` opts this story into the test-runner axe gate
 * (.storybook/test-runner.ts). The launcher is shippable UI — the SPR-08 gate
 * audits it like any other surface, not as an exception.
 */
const meta = {
  title: "Navigation / ProductsLauncher",
  component: ProductsLauncher,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof ProductsLauncher>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Open the launcher on mount by dispatching the real toggle event. */
export const Open: Story = {
  render: () => {
    useEffect(() => {
      window.dispatchEvent(new Event("antiek:launcher:toggle"));
    }, []);
    return (
      <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">
        <ProductsLauncher />
      </div>
    );
  },
};
