import "./animations.css";
import BrainMascot from "../../BrainMascot";

/**
 * The Antiek brain, tobogganing — used as a loading spinner.
 *
 * Brand § 10: ~6 fps wobble, rotate -3°/+3° at 200ms intervals;
 * speed lines flicker. Use for the streaming-investigation banner
 * and other "long-running, expected" loading states.
 *
 * Sizes 24 / 32 / 64 are the recommended steps. Anything in between
 * works because the SVG scales.
 *
 * Core mark delegated to <BrainMascot mood="idle" /> + --mascot-* tokens
 * for any remaining accents. No more parallel geometry fork.
 */
type Props = {
  size?: number;
  label?: string;
};

export default function BrainTobogganSpinner({
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
      {/* Speed lines and toboggan slat remain pose chrome. The Brain body
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
          className="mascot-toboggan-speedlines"
          opacity={0.55}
        >
          <line x1="0" y1="14" x2="14" y2="14" />
          <line x1="0" y1="22" x2="10" y2="22" />
          <line x1="0" y1="30" x2="16" y2="30" />
        </g>
        {/* Toboggan slat only — BrainMascot supplies the leaning body */}
        <g className="mascot-toboggan">
          <rect x="14" y="32" width="38" height="3" rx="1" fill="var(--mascot-coat)" />
          <line x1="18" y1="36" x2="18" y2="40" stroke="var(--mascot-coat)" strokeWidth="1.5" />
          <line x1="48" y1="36" x2="48" y2="40" stroke="var(--mascot-coat)" strokeWidth="1.5" />
        </g>
      </svg>
      <BrainMascot mood="idle" size={size} className="mascot-toboggan" style={{ position: "absolute", left: "25%", top: "8%" }} />
    </span>
  );
}
