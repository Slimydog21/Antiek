import "./animations.css";
import WernerAuthoredPose from "../WernerAuthoredPose";

/**
 * Werner the penguin, sleeping — idle screen / empty state.
 *
 * Brand § 10: belly breathes (scaleY 1.0 ↔ 1.04 over 2.4s); zZz
 * letters drift upward + fade. Use as the empty-state mascot for
 * routes with no current activity (no active investigation, no
 * outcomes graded, no notebooks).
 *
 * Both animated layers use the same centrally mapped authored raster. The
 * body and Z marks occupy disjoint vertical bands in that source, so clipping
 * lets them keep independent motion without redrawing or duplicating chrome.
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
      {reduced ? (
        <WernerAuthoredPose
          pose="sleeping"
          size={size}
          className="werner-sleep-layer werner-sleep-still"
        />
      ) : (
        <>
          <WernerAuthoredPose
            pose="sleeping"
            size={size}
            className="werner-sleep-layer werner-sleep-body"
          />
          <WernerAuthoredPose
            pose="sleeping"
            size={size}
            className="werner-sleep-layer werner-sleep-zzz-layer"
          />
        </>
      )}
    </span>
  );
}
