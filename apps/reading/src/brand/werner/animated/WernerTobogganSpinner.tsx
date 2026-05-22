import "./animations.css";

/**
 * Werner the penguin, tobogganing — used as a loading spinner.
 *
 * Brand § 10: ~6 fps wobble, rotate -3°/+3° at 200ms intervals;
 * speed lines flicker. Use for the streaming-investigation banner
 * and other "long-running, expected" loading states.
 *
 * Sizes 24 / 32 / 64 are the recommended steps. Anything in between
 * works because the SVG scales.
 */
type Props = {
  size?: number;
  label?: string;
};

export default function WernerTobogganSpinner({
  size = 32,
  label = "Loading…",
}: Props) {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-block align-middle"
      style={{ width: size, height: size }}
    >
      <svg
        viewBox="0 0 64 48"
        width={size}
        height={size}
        aria-hidden="true"
      >
        {/* Speed lines — three muted strokes behind Werner. */}
        <g
          stroke="currentColor"
          strokeWidth="1.5"
          className="werner-toboggan-speedlines"
          opacity={0.55}
        >
          <line x1="0" y1="14" x2="14" y2="14" />
          <line x1="0" y1="22" x2="10" y2="22" />
          <line x1="0" y1="30" x2="16" y2="30" />
        </g>
        {/* Werner + toboggan. Wobble rotates the whole group. */}
        <g className="werner-toboggan">
          {/* Toboggan slat */}
          <rect x="14" y="32" width="38" height="3" rx="1" fill="#0F1419" />
          <line
            x1="18"
            y1="36"
            x2="18"
            y2="40"
            stroke="#0F1419"
            strokeWidth="1.5"
          />
          <line
            x1="48"
            y1="36"
            x2="48"
            y2="40"
            stroke="#0F1419"
            strokeWidth="1.5"
          />
          {/* Werner body — leaning forward */}
          <ellipse cx="32" cy="22" rx="11" ry="13" fill="#0F1419" />
          <ellipse cx="32" cy="25" rx="7" ry="10" fill="#EEF1F6" />
          {/* Eyes (closed because focused) */}
          <line
            x1="27.5"
            y1="17"
            x2="29.5"
            y2="17"
            stroke="#0F1419"
            strokeWidth="1.2"
          />
          <line
            x1="34.5"
            y1="17"
            x2="36.5"
            y2="17"
            stroke="#0F1419"
            strokeWidth="1.2"
          />
          {/* Bill */}
          <path d="M30 20 L32 23 L34 20 Z" fill="#F5DF24" />
          {/* Feet folded under */}
          <ellipse cx="28" cy="34" rx="2.2" ry="0.9" fill="#F5DF24" />
          <ellipse cx="36" cy="34" rx="2.2" ry="0.9" fill="#F5DF24" />
        </g>
      </svg>
    </span>
  );
}
