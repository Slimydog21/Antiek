import "./animations.css";
import Werner from "../../Werner";

/**
 * Werner the penguin, waddling — route-navigation transition.
 *
 * Brand § 10: 3-frame loop (left-foot, both-feet, right-foot) over
 * 300ms total + 2° body rotation for the waddle bob. Use as a
 * sub-route transition between modes when the operator clicks G+I
 * / G+W / G+N — a quick "Werner is walking you over" beat.
 *
 * Default size 32 fits between the NavRail icons. The transition
 * helper that owns the "show Werner during nav" lifecycle lives in
 * `useWaddleTransition` (sibling file).
 *
 * Core mark delegated to <Werner mood="idle" /> + --werner-* tokens
 * for any remaining accents. No more parallel geometry fork.
 */
type Props = { size?: number; label?: string };

export default function WernerWaddle({
  size = 32,
  label = "Navigating",
}: Props) {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-block align-middle"
      style={{ width: size, height: size }}
    >
      {/* Core mark now single-source from canonical Werner at rail fidelity.
          The waddle chrome (body bob + foot lift) is applied via the
          container class; the penguin geometry itself is no longer forked. */}
      <Werner mood="idle" size={size} className="werner-waddle" />
    </span>
  );
}
