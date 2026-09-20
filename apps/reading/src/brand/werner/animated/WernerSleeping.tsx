import "./animations.css";
import BrainMascot from "../../BrainMascot";

/**
 * The brain, sleeping — idle screen / empty state.
 *
 * The empty mood (Krea sleepy pose) renders the resting brain; three zZz
 * letters drift upward + fade as pose chrome. Use as the empty-state mascot
 * for routes with no current activity (no active investigation, no outcomes
 * graded, no notebooks).
 */
type Props = { size?: number; label?: string; reduced?: boolean };

export default function WernerSleeping({
  size = 96,
  label = "No activity",
  reduced = false,
}: Props) {
  return (
    <span
      role="img"
      aria-label={label}
      className="inline-block align-middle"
      data-reduced={String(reduced)}
      style={{ width: size, height: size, position: "relative" }}
    >
      <span
        className={reduced ? "werner-sleep-layer werner-sleep-still" : "werner-sleep-layer werner-sleep-body"}
        aria-hidden="true"
      >
        <BrainMascot mood="empty" size={size} />
      </span>
      {/* The zZz chrome — decorative drift, present only when animating. */}
      {!reduced && (
        <span className="werner-sleep-zzz-layer" aria-hidden="true">
          <svg
            viewBox="0 0 64 64"
            width={size}
            height={size}
            style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}
          >
            <g fill="var(--werner-coat)" fontFamily="ui-monospace, monospace" fontWeight="700">
              <text x="46" y="22" fontSize="10" className="werner-zzz">z</text>
              <text x="42" y="28" fontSize="13" className="werner-zzz werner-zzz-2">z</text>
              <text x="38" y="36" fontSize="16" className="werner-zzz werner-zzz-3">Z</text>
            </g>
          </svg>
        </span>
      )}
    </span>
  );
}
