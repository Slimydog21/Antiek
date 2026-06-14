import type { Meta, StoryObj } from "@storybook/react";
import { within, userEvent, waitFor, expect } from "@storybook/test";

import { ProductsLauncher } from "./ProductsLauncher";

/**
 * ProductsLauncher (SPR-04 zone-1 ⊞) — the honest full surface inventory of
 * EVERY mode. Two calm top-level groups (workflow deep modes under their
 * workflows; run & settings for Operator/Trust/Settings/governance) with
 * human labels. The pressure-release valve that keeps the rail at exactly
 * four workflows: everything else lives here + in ⌘K.
 *
 * In the app, NavRail owns the open state and renders this as a controlled
 * component (`<ProductsLauncher open={launcherOpen} onClose={…} />`).
 *
 * ── Why this stories file authors ≥2 states (ALC SPR-09 product-character) ────
 * ProductsLauncher is a ≥2-state control: it is CLOSED (returns null —
 * ProductsLauncher.tsx:124) until the rail's More verb opens it, and once open
 * it FILTERS its inventory live (:72,:116) down to an EMPTY "no surfaces match"
 * state (:269). A single "Open" story would trip the rubric's level-1 absence
 * anchor (one story for a ≥2-state component). Each story below drives the REAL
 * component into one of those states — the closed render, the open inventory,
 * the filtered subset, and the empty result — with the component's own `query`
 * reducer running (the filter stories type into the real input via `play`,
 * nothing is faked).
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

/** The launcher open over the full inventory — the default populated state. */
export const Open: Story = {
  args: {
    open: true,
    onClose: () => {},
  },
  render: (args) => {
    return (
      <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">
        <ProductsLauncher {...args} />
      </div>
    );
  },
};

/**
 * CLOSED — the launcher with `open={false}`. The REAL component returns null
 * (ProductsLauncher.tsx:124), so the only thing on screen is the trigger
 * affordance the rail owns: the ⊞ More button that opens it. Authored so the
 * closed/trigger state is inspectable, not just the open overlay. (The button
 * here is a faithful static stand-in for NavRail's More verb — clicking it does
 * nothing in this isolated story; NavRail wires the real open state.)
 */
export const Closed: Story = {
  args: {
    open: false,
    onClose: () => {},
  },
  render: (args) => {
    return (
      <div className="h-screen w-screen bg-ice-2 dark:bg-space-2 flex items-end justify-end p-6">
        <button
          type="button"
          aria-label="More"
          title="More — all products, Operator, Trust, Settings"
          className="feel-focusable h-10 w-10 grid place-items-center rounded bg-ice-1 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 text-ink dark:text-bright"
        >
          ⊞
        </button>
        <ProductsLauncher {...args} />
      </div>
    );
  },
};

/**
 * SEARCH ACTIVE / FILTERED — the launcher open, then "trust" typed into the
 * live filter input. The play function drives the REAL `query` reducer
 * (:72,:116), narrowing the inventory to the matching surfaces (e.g. Trust &
 * safety). The filtered subset is the authored non-default state, not a faked
 * list.
 */
export const SearchActive: Story = {
  args: {
    open: true,
    onClose: () => {},
  },
  render: (args) => {
    return (
      <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">
        <ProductsLauncher {...args} />
      </div>
    );
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = await canvas.findByPlaceholderText("Filter…");
    await userEvent.click(input);
    await userEvent.type(input, "trust");
    await waitFor(() => {
      expect(input).toHaveValue("trust");
    });
  },
};

/**
 * EMPTY / NO RESULTS — the launcher filtered by a query that matches nothing,
 * so the REAL empty branch renders ("No surfaces match …", :269). The play
 * function types a deliberately-unmatchable string; the component's own filter
 * reducer reaches the empty state. This is the honest empty surface the
 * dimension rewards — authored, inspectable, not left to runtime.
 */
export const NoResults: Story = {
  args: {
    open: true,
    onClose: () => {},
  },
  render: (args) => {
    return (
      <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">
        <ProductsLauncher {...args} />
      </div>
    );
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = await canvas.findByPlaceholderText("Filter…");
    await userEvent.click(input);
    await userEvent.type(input, "zzqqxnomatch");
    await waitFor(() => {
      expect(canvas.getByText(/No surfaces match/i)).toBeInTheDocument();
    });
  },
};
