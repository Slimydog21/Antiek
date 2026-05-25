import "./animations.css";
import Werner from "../../Werner";

/**
 * Werner the penguin, tobogganing — used as a loading spinner.
 *
 * Brand § 10: ~6 fps wobble, rotate -3°/+3° at 200ms intervals;
 * speed lines flicker. Use for the streaming-investigation banner
 * and other "long-running, expected" loading states.
 *
 * Sizes 24 / 32 / 64 are the recommended steps. Anything in between
 * works because the SVG scales.
 *
 * Core mark delegated to <Werner mood="idle" /> + --werner-* tokens
 * for any remaining accents. No more parallel geometry fork.
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
      style={{ width: size, height: size, position: "relative" }}
    >
      {/* Speed lines and toboggan slat remain pose chrome. The Werner body
          itself is fully delegated (single source at all fidelities). */}
      <svg
        viewBox="0 0 64 48"
        width={size}
        height={size}
        aria-hidden="true"
        style={{ position: "absolute", left: 0, top: 0 }}
      >
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
        {/* Toboggan slat only — Werner supplies the leaning penguin body */}
        <g className="werner-toboggan">
          <rect x="14" y="32" width="38" height="3" rx="1" fill="var(--werner-coat)" />
          <line x1="18" y1="36" x2="18" y2="40" stroke="var(--werner-coat)" strokeWidth="1.5" />
          <line x1="48" y1="36" x2="48" y2="40" stroke="var(--werner-coat)" strokeWidth="1.5" />
        </g>
      </svg>
      <Werner mood="idle" size={size} className="werner-toboggan" style={{ position: "absolute", left: "25%", top: "8%" }} />
    </span>
  );
}
