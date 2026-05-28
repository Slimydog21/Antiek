import type { Meta, StoryObj } from "@storybook/react";

import { PenguinMascot } from "./PenguinMascot";

/**
 * PenguinMascot (SPR-12 M3) — the floating project home, now an AUTONOMOUS
 * WADDLER (SPR-06 M5).
 *
 * The mascot positions itself `fixed` over the whole app, so the stories
 * give it a full-bleed surface to float over. Visual baselines here cover
 * the mark's resting appearance in light + dark (the toolbar theme switch
 * drives the dark frame). The behaviour — click→float, drag, double-click→
 * open, AUTONOMOUS ROAM (walks the viewport on a chained timeout), bounded,
 * reduced-motion-still, drag-pauses-roam — is asserted in
 * PenguinMascot.test.tsx, the deterministic substitute for a flaky
 * motion snapshot.
 *
 * Reduced motion: the roam (and the idle wander) read the live OS / a11y-
 * addon `prefers-reduced-motion` setting via usePrefersReducedMotion. To see
 * the still variant in Storybook, toggle reduced motion (OS Accessibility, or
 * the a11y addon) and reload Roaming — Werner parks and stops walking while
 * staying fully clickable. The ReducedMotionNote story documents this; the
 * mechanical guarantee is the "does NOT roam under prefers-reduced-motion"
 * test (a Storybook toggle is not a gate).
 */
const meta = {
  title: "Shell / PenguinMascot (SPR-06)",
  component: PenguinMascot,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof PenguinMascot>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The mascot at rest over a blank surface — the logo-fix payoff is visible
 *  here too: no white box around the penguin on either theme. */
export const Resting: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">
      <PenguinMascot />
    </div>
  ),
};

/** Autonomous roam — over a full-bleed surface with mock working content, so
 *  the pointer-events isolation is visible: Werner roams ON TOP of the text
 *  but the text underneath stays selectable (only the penguin captures
 *  pointer events). Watch a few seconds: he picks a new spot + ambles there. */
export const Roaming: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2 p-12">
      <article className="prose max-w-2xl text-ink dark:text-bright">
        <h1 className="text-2xl font-bold mb-3">Working region</h1>
        <p className="text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
          Werner roams this surface autonomously. He never blocks this text —
          the container is pointer-events:none-free (he is the only fixed
          element) and only the penguin himself captures clicks, so you can
          still select and interact with everything underneath him.
        </p>
      </article>
      <PenguinMascot />
    </div>
  ),
};

/** Reduced-motion behaviour note. Under prefers-reduced-motion Werner does
 *  NOT roam — he parks where he is and stays clickable (no walking, no
 *  wander, no busy-loop). Toggle reduced motion to verify; the test pins it. */
export const ReducedMotionNote: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2 p-12">
      <div className="max-w-md text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
        With <code className="font-mono">prefers-reduced-motion: reduce</code>{" "}
        set, Werner stays put — no autonomous roam, no idle wander — and remains
        a clickable control (single-click floats the project tree, double-click
        opens the project). Toggle reduced motion in your OS / the a11y addon
        and reload to see the still variant.
      </div>
      <PenguinMascot />
    </div>
  ),
};
