import "./animations.css";
import WernerAuthoredPose from "../WernerAuthoredPose";

type Props = { size?: number; reduced?: boolean };

export default function WernerWaking({ size = 96, reduced = false }: Props) {
  return (
    <span
      aria-hidden="true"
      data-werner-waking="true"
      data-reduced={String(reduced)}
      className={reduced ? undefined : "werner-waking"}
      style={{ display: "block", width: size, height: size }}
    >
      <WernerAuthoredPose pose="waking" size={size} />
    </span>
  );
}
