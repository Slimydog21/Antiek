import "./animations.css";
import WernerAuthoredPose from "../WernerAuthoredPose";

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
 * SPR-23: The generic idle-body approximation is replaced with the
 * authored low-slide body (WernerAuthoredPose, private tobogganing
 * vocabulary). The invented SVG sled slat is removed — the approved
 * illustration is a belly-slide pose, and adding a vehicle changes
 * its meaning. Speed lines remain code-native SVG for deterministic
 * timing, theming, and reduced-motion collapse.
 */
type Props = {
  size?: number;
  label?: string;
  reduced?: boolean;
};

export default function WernerTobogganSpinner({
  size = 32,
  label = "Loading…",
  reduced = false,
}: Props) {
  return (
    <span
      role="status"
      aria-label={label}
      className={`inline-block align-middle${reduced ? " werner-toboggan-static" : ""}`}
      style={{ width: size, height: size, position: "relative" }}
    >
      {/* Speed lines — decorative code-native SVG layer. The authored body
          is a separate image layer via WernerAuthoredPose. */}
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
          opacity={reduced ? 0 : 0.55}
        >
          <line x1="0" y1="14" x2="14" y2="14" />
          <line x1="0" y1="22" x2="10" y2="22" />
          <line x1="0" y1="30" x2="16" y2="30" />
        </g>
      </svg>
      {/* Authored tobogganing body — the only runtime importer of the
          private body asset. werner-toboggan class applies the 1200ms
          six-step wobble; transform-origin 50% 70% centres the rotation
          on the penguin's belly. */}
      <WernerAuthoredPose
        pose="tobogganing"
        size={size}
        className="werner-toboggan"
        style={{ position: "absolute", left: 0, top: 0 }}
      />
    </span>
  );
}
