import type { Meta, StoryObj } from "@storybook/react";

import { MascotStation } from "./MascotStation";

/**
 * MascotStation (SPR-12 M3) — the floating project home, now a FIXED STATION
 * (2026-07-02). Brain does NOT chase the cursor and does NOT wander off; he
 * stands at his station and the cursor is the bait on his fishing line. See
 * docs/htmlspec/werner-fixed-station/DESIGN.md.
 *
 * The mascot positions itself `fixed` over the whole app, so the stories give
 * it a full-bleed surface to stand on. Visual baselines here cover the mark's
 * resting appearance in light + dark (the toolbar theme switch drives the dark
 * frame). The behaviour — click→float, drag→re-station, double-click→open, the
 * pointer-idle own-hole gag, and "never follows the cursor" — is asserted in
 * MascotStation.test.tsx + MascotStation.station.test.tsx, the deterministic
 * substitutes for a flaky motion snapshot.
 *
 * NOTE ON STORY IDS: the meta title + the export names (Resting/Roaming/
 * ReducedMotionNote) are FROZEN — the operator-run e2e pixel gates
 * (e2e/_ams/mascot.spec.ts) resolves the mascot by those exact
 * story ids (shell-mascotstation-spr-06--roaming etc.). The "Roaming" export
 * name is now historical (Brain no longer roams); it is kept only so those
 * gates keep resolving. Rename it (and update every referencing spec's id) in a
 * dedicated change, never incidentally.
 *
 * Reduced motion: the station gag + idle wander read the live OS / a11y-addon
 * `prefers-reduced-motion` setting via usePrefersReducedMotion. Toggle it and
 * reload — Brain holds a still frame while staying fully clickable. The
 * ReducedMotionNote story documents this; the mechanical guarantee is the
 * reduced-motion tests (a Storybook toggle is not a gate).
 */
const meta = {
  title: "Shell / MascotStation (SPR-06)",
  component: MascotStation,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof MascotStation>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The mascot at rest over a blank surface — the logo-fix payoff is visible
 *  here too: no white box around the mascot on either theme. */
export const Resting: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2">
      <MascotStation />
    </div>
  ),
};

/** Brain at his station over a full-bleed surface with mock working content,
 *  so the pointer-events isolation is visible: he stands ON TOP of the text but
 *  the text underneath stays selectable (only the mascot captures pointer
 *  events). Leave the pointer still a couple seconds and his own-hole fishing
 *  gag plays; he never walks off, and he never chases the cursor.
 *  (Export name kept as `Roaming` only to freeze the e2e story id — see the
 *  meta docblock.) */
export const Roaming: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2 p-12">
      <article className="prose max-w-2xl text-ink dark:text-bright">
        <h1 className="text-2xl font-bold mb-3">Working region</h1>
        {/* LOSTPIXEL PIXEL-FREEZE: visible wording still says "Werner"/
            "penguin" on purpose — the shell-penguin-mascot-spr-06--* baselines
            (renamed to shell-mascot-station-spr-06--*) were not re-minted, so
            canvas pixels must stay identical. Purge with the re-mint PR. */}
        <p className="text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
          Werner holds his station here. He never blocks this text — he is the
          only fixed element and only the penguin himself captures clicks, so you
          can still select and interact with everything underneath him. Leave the
          mouse still and watch him fish his own little hole; move it and he
          treats the cursor as his bait — but he never leaves his spot.
        </p>
      </article>
      <MascotStation />
    </div>
  ),
};

/** Reduced-motion behaviour note. Under prefers-reduced-motion Brain holds a
 *  still frame — no fishing gag, no idle wander — and remains a clickable
 *  control (single-click floats the project tree, double-click opens the
 *  project). Toggle reduced motion in your OS / the a11y addon and reload to
 *  see the still variant. */
export const ReducedMotionNote: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2 p-12">
      <div className="max-w-md text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
        {/* LOSTPIXEL PIXEL-FREEZE: visible "Werner" wording kept until the
            shell-mascot-station-spr-06--* baselines are re-minted. */}
        With <code className="font-mono">prefers-reduced-motion: reduce</code>{" "}
        set, Werner stays put — no fishing gag, no idle wander — and remains a
        clickable control (single-click floats the project tree, double-click
        opens the project). Toggle reduced motion in your OS / the a11y addon and
        reload to see the still variant.
      </div>
      <MascotStation />
    </div>
  ),
};
