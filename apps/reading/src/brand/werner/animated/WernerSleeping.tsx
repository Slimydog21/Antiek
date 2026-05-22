import "./animations.css";

/**
 * Werner the penguin, sleeping — idle screen / empty state.
 *
 * Brand § 10: belly breathes (scaleY 1.0 ↔ 1.04 over 2.4s); zZz
 * letters drift upward + fade. Use as the empty-state mascot for
 * routes with no current activity (no active investigation, no
 * outcomes graded, no notebooks).
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
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden="true">
        {/* Werner curled up — body breathes. */}
        <g className="werner-sleep-body">
          <ellipse cx="32" cy="44" rx="20" ry="12" fill="#0F1419" />
          <ellipse cx="32" cy="46" rx="14" ry="8" fill="#EEF1F6" />
          {/* Closed eye (just one visible — head turned). */}
          <path
            d="M22 38 Q24 36 26 38"
            stroke="#0F1419"
            strokeWidth="1.5"
            fill="none"
          />
          {/* Bill tucked into belly */}
          <path d="M19 41 L21 44 L23 41 Z" fill="#F5DF24" opacity="0.85" />
        </g>
        {/* Three zZz letters drifting up + fading. */}
        <g
          fill="#0F1419"
          fontFamily="ui-monospace, monospace"
          fontWeight="700"
        >
          <text
            x="46"
            y="22"
            fontSize="10"
            className="werner-zzz"
          >
            z
          </text>
          <text
            x="42"
            y="28"
            fontSize="13"
            className="werner-zzz werner-zzz-2"
          >
            z
          </text>
          <text
            x="38"
            y="36"
            fontSize="16"
            className="werner-zzz werner-zzz-3"
          >
            Z
          </text>
        </g>
      </svg>
    </span>
  );
}
