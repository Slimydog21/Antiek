import "./animations.css";
import WernerAuthoredPose from "../WernerAuthoredPose";

type Props = { size?: number; reduced?: boolean };

/** One awake, non-looping acknowledgement of a real scene nightfall edge. */
export default function WernerNightWatch({ size = 96, reduced = false }: Props) {
  return (
    <span
      aria-hidden="true"
      data-werner-night-watch="true"
      data-reduced={String(reduced)}
      className={reduced ? undefined : "werner-night-watch"}
      style={{ display: "block", width: size, height: size }}
    >
      <WernerAuthoredPose pose="nightWatch" size={size} />
    </span>
  );
}
