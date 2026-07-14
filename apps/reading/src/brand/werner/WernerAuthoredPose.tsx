import type { CSSProperties } from "react";

import wernerHeadTilt from "./poses/werner_head_tilt_v1_transparent.png";
import wernerSleeping from "./poses/werner_sleeping_v1_transparent.png";

/**
 * Authored illustration poses used inside sanctioned animated wrappers.
 *
 * These are not product moods. `Werner.tsx` retains the complete four-mood
 * public contract; this private vocabulary prevents wrappers from importing
 * pose files directly or substituting a semantically unrelated mood.
 */
const AUTHORED_POSE = {
  headTilt: wernerHeadTilt,
  sleeping: wernerSleeping,
} as const;

type Props = {
  pose: keyof typeof AUTHORED_POSE;
  size: number;
  className?: string;
  style?: CSSProperties;
};

export default function WernerAuthoredPose({
  pose,
  size,
  className,
  style,
}: Props) {
  return (
    <img
      src={AUTHORED_POSE[pose]}
      alt=""
      aria-hidden="true"
      data-werner-authored-pose={pose}
      width={size}
      height={size}
      className={className}
      style={{
        display: "block",
        width: size,
        height: size,
        objectFit: "contain",
        ...style,
      }}
      draggable={false}
    />
  );
}
