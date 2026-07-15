import type { Meta, StoryObj } from "@storybook/react";

import { PenguinMascot } from "./PenguinMascot";
import WernerRig from "../werner/WernerRig";

/**
 * PenguinMascot (SPR-12 M3) — the floating project home, now a FIXED STATION
 * (2026-07-02). Werner does NOT chase the cursor and does NOT wander off; he
 * stands at his station and the cursor is the bait on his fishing line. See
 * docs/htmlspec/werner-fixed-station/DESIGN.md.
 *
 * The mascot positions itself `fixed` over the whole app, so the stories give
 * it a full-bleed surface to stand on. Visual baselines here cover the mark's
 * resting appearance in light + dark (the toolbar theme switch drives the dark
 * frame). The behaviour — click→float, drag→re-station, double-click→open, the
 * pointer-idle own-hole gag, and "never follows the cursor" — is asserted in
 * PenguinMascot.test.tsx + PenguinMascot.station.test.tsx, the deterministic
 * substitutes for a flaky motion snapshot.
 *
 * NOTE ON STORY IDS: the meta title + the export names (Resting/Roaming/
 * ReducedMotionNote) are FROZEN — the operator-run e2e pixel gates
 * (e2e/_ams/penguin.spec.ts, e2e/_werner/*) resolve the mascot by those exact
 * story ids (shell-penguinmascot-spr-06--roaming etc.). The "Roaming" export
 * name is now historical (Werner no longer roams); it is kept only so those
 * gates keep resolving. Rename it (and update every referencing spec's id) in a
 * dedicated change, never incidentally.
 *
 * Reduced motion: the station gag + idle wander read the live OS / a11y-addon
 * `prefers-reduced-motion` setting via usePrefersReducedMotion. Toggle it and
 * reload — Werner holds a still frame while staying fully clickable. The
 * ReducedMotionNote story documents this; the mechanical guarantee is the
 * reduced-motion tests (a Storybook toggle is not a gate).
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

/** Werner at his station over a full-bleed surface with mock working content,
 *  so the pointer-events isolation is visible: he stands ON TOP of the text but
 *  the text underneath stays selectable (only the penguin captures pointer
 *  events). Leave the pointer still a couple seconds and his own-hole fishing
 *  gag plays; he never walks off, and he never chases the cursor.
 *  (Export name kept as `Roaming` only to freeze the e2e story id — see the
 *  meta docblock.) */
export const Roaming: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2 p-12">
      <article className="prose max-w-2xl text-ink dark:text-bright">
        <h1 className="text-2xl font-bold mb-3">Working region</h1>
        <p className="text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
          Werner holds his station here. He never blocks this text — he is the
          only fixed element and only the penguin himself captures clicks, so you
          can still select and interact with everything underneath him. Leave the
          mouse still and watch him fish his own little hole; move it and he
          treats the cursor as his bait — but he never leaves his spot.
        </p>
      </article>
      <PenguinMascot />
    </div>
  ),
};

/** Reduced-motion behaviour note. Under prefers-reduced-motion Werner holds a
 *  still frame — no fishing gag, no idle wander — and remains a clickable
 *  control (single-click floats the project tree, double-click opens the
 *  project). Toggle reduced motion in your OS / the a11y addon and reload to
 *  see the still variant. */
export const ReducedMotionNote: Story = {
  render: () => (
    <div className="h-screen w-screen bg-ice-2 dark:bg-space-2 p-12">
      <div className="max-w-md text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
        With <code className="font-mono">prefers-reduced-motion: reduce</code>{" "}
        set, Werner stays put — no fishing gag, no idle wander — and remains a
        clickable control (single-click floats the project tree, double-click
        opens the project). Toggle reduced motion in your OS / the a11y addon and
        reload to see the still variant.
      </div>
      <PenguinMascot />
    </div>
  ),
};

/**
 * SPR-24 — Deterministic station-body fidelity plate.
 *
 * Renders the WernerRig at native 64px on both light and dark surfaces, plus
 * a neutral still reference, so a Storybook reviewer can verify:
 *   - the authored station body is recognizable at 64px
 *   - no duplicate limb, yellow gap, floating butt, cap-over-hand, clipping,
 *     chroma fringe, or scale jump exists on either theme
 *   - the rod protrudes correctly behind the body
 *   - reduced motion holds a still frame (no fishing gag, no idle wander)
 *
 * This is a visual regression anchor — not a behaviour test. The behaviour
 * (click→float, drag→re-station, fishing loop timing) is asserted in
 * PenguinMascot.test.tsx + PenguinMascot.station.test.tsx.
 */
export const StationBodyFidelity: Story = {
  render: () => (
    <div className="flex flex-col gap-8 p-8">
      {/* Light surface */}
      <section>
        <h2 className="mb-2 font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
          Light surface — 64px native
        </h2>
        <div className="flex items-center gap-6 rounded-hog border border-rule bg-ice-0 p-6 dark:bg-charcoal-2">
          <div className="flex items-center justify-center" style={{ width: 64, height: 64 }}>
            <WernerRig size={64} label="Project" />
          </div>
          <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
            Authored body + code rod + line/fish foreground
          </span>
        </div>
      </section>

      {/* Dark surface */}
      <section>
        <h2 className="mb-2 font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
          Dark surface — 64px native
        </h2>
        <div className="flex items-center gap-6 rounded-hog border border-rule bg-charcoal-2 p-6">
          <div className="flex items-center justify-center" style={{ width: 64, height: 64 }}>
            <WernerRig size={64} label="Project" />
          </div>
          <span className="font-mono text-[10px] text-moonlight">
            No chroma fringe, no ghost backdrop on dark
          </span>
        </div>
      </section>

      {/* Neutral still: the media-query substitution itself is mechanically tested. */}
      <section>
        <h2 className="mb-2 font-mono text-xs uppercase tracking-wider text-ink-soft dark:text-starlight">
          Neutral still — reduced-motion fallback
        </h2>
        <div className="flex items-center gap-6 rounded-hog border border-rule bg-ice-0 p-6 dark:bg-charcoal-2">
          <div className="flex items-center justify-center" style={{ width: 64, height: 64 }}>
            <WernerRig size={64} label="Project" />
          </div>
          <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
            Reduced-motion media query is covered by deterministic tests
          </span>
        </div>
      </section>
    </div>
  ),
};
