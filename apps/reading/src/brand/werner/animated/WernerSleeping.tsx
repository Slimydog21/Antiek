import "./animations.css";
import Werner from "../../Werner";

/**
 * Werner the penguin, sleeping — idle screen / empty state.
 *
 * Brand § 10: belly breathes (scaleY 1.0 ↔ 1.04 over 2.4s); zZz
 * letters drift upward + fade. Use as the empty-state mascot for
 * routes with no current activity (no active investigation, no
 * outcomes graded, no notebooks).
 *
 * Core mark delegated to <Werner mood="empty" /> + --werner-* tokens
 * for any remaining accents. No more parallel geometry fork.
 */
type Props = { size?: number; label?: string };

export default function WernerSleeping({
  size = 96,
  label = "No activity",
}: Props) {
  return (
    <span
      role="img"
      aria-label={label}
      className="inline-block align-middle"
      style={{ width: size, height: size, position: "relative" }}
    >
      {/* Core mark delegated; the curled pose is approximated by empty mood
          at large size. The zZz chrome and breath class remain on the wrapper. */}
      <Werner mood="empty" size={size} className="werner-sleep-body" />
      {/* Three zZz letters drifting up + fading (pose chrome only). */}
      <svg
        viewBox="0 0 64 64"
        width={size}
        height={size}
        style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}
        aria-hidden="true"
      >
        <g fill="var(--werner-coat)" fontFamily="ui-monospace, monospace" fontWeight="700">
          <text x="46" y="22" fontSize="10" className="werner-zzz">z</text>
          <text x="42" y="28" fontSize="13" className="werner-zzz werner-zzz-2">z</text>
          <text x="38" y="36" fontSize="16" className="werner-zzz werner-zzz-3">Z</text>
        </g>
      </svg>
    </span>
  );
}
