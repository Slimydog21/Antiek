import BrainMascot from "../../brand/BrainMascot";

/**
 * CelebrateBurst — the visible half of a signature delight beat (U-05 M2).
 *
 * Renders U-02's Brain in the `celebrate` mood (the one-shot raised
 * flipper + sparkle) while `active` is true, and nothing when it isn't.
 * Pair it with useCelebrate() — that hook owns the once-and-retire timing;
 * this component is pure render.
 *
 * Non-blocking by construction: the burst is a `pointer-events-none`
 * overlay, so it never covers the result it's celebrating — the operator
 * can click straight through it. It carries `aria-hidden` because the beat
 * is decoration; the payoff state announces itself through its own
 * surface's `role="status"` (e.g. StartResearch's working banner). Brain
 * is one of its four sanctioned slots here — "core action completed" —
 * per brand/README.md's restraint rule.
 *
 * Reduced-motion: Brain's celebrate keyframe collapses to a static
 * sparkle frame via mascot/animated/animations.css, so under reduced
 * motion this still shows the mascot, just without the lift/twinkle.
 */
type Props = {
  /** Whether the beat is in its window (useCelebrate().celebrating). */
  active: boolean;
  /** Brain size in px. Beat default 64 (character fidelity). */
  size?: number;
  className?: string;
};

export default function CelebrateBurst({
  active,
  size = 64,
  className,
}: Props) {
  if (!active) return null;
  return (
    <span
      aria-hidden="true"
      className={
        className
          ? `pointer-events-none inline-flex ${className}`
          : "pointer-events-none inline-flex"
      }
    >
      <BrainMascot mood="celebrate" size={size} />
    </span>
  );
}
