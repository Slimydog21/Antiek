import type { Meta, StoryObj } from "@storybook/react";

import IglooMark from "./IglooMark";

/**
 * IglooMark (SPR-06 M4) — the home control's mark.
 *
 * The igloo replaces the static top-left penguin as the home door (the
 * operator's ask). It renders on the sun-yellow rail home button exactly as
 * the penguin did — so the OnRailButton story reproduces that exact frame
 * (28px, on a sun button with the 2px ink border) to prove it matches the
 * brand palette + Lemon-UI weight. The Sizes story shows it stays crisp
 * vector from rail size up to a hero size.
 *
 * The control's a11y (link role, aria-label, focus ring) lives on the
 * wrapping button in NavRail, not the mark — see NavRail.stories.tsx +
 * navrail.panel.test.tsx for the accessible-home-control coverage.
 */
const meta = {
  title: "Brand / Werner / IglooMark (SPR-06)",
  component: IglooMark,
  parameters: { layout: "centered" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof IglooMark>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The mark exactly as it sits on the rail's sun-yellow home button:
 *  28px, ink 2px border, sun fill — the frame it replaces the penguin in. */
export const OnRailButton: Story = {
  render: () => (
    <div className="flex h-12 w-12 items-center justify-center border-b-edge border-sun bg-sun/95">
      <IglooMark size={28} />
    </div>
  ),
};

/** Vector crispness from rail (28) up to hero (96) — same paths, no raster. */
export const Sizes: Story = {
  render: () => (
    <div className="flex items-end gap-8 bg-ice-2 dark:bg-space-2 p-8">
      {[28, 48, 96].map((s) => (
        <div key={s} className="flex flex-col items-center gap-1.5">
          <IglooMark size={s} />
          <div className="font-mono text-[10px] text-ink-mute">{s}px</div>
        </div>
      ))}
    </div>
  ),
};
