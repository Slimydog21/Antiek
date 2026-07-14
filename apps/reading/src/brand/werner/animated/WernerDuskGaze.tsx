import "./animations.css";
import WernerAuthoredPose from "../WernerAuthoredPose";

type Props = { size?: number; reduced?: boolean };

/** One quiet, non-looping acknowledgement of a real scene dusk transition. */
export default function WernerDuskGaze({ size = 96, reduced = false }: Props) {
  return (
    <span
      aria-hidden="true"
      data-werner-dusk-gaze="true"
      data-reduced={String(reduced)}
      className={reduced ? undefined : "werner-dusk-gaze"}
      style={{ display: "block", width: size, height: size }}
    >
      <WernerAuthoredPose pose="duskGaze" size={size} />
    </span>
  );
}
