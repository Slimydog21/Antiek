import type { CSSProperties } from "react";

import wernerHeadTilt from "./poses/werner_head_tilt_v1_transparent.png";
import wernerDuskGaze from "./poses/werner_dusk_gaze_v1_transparent.png";
import wernerSleeping from "./poses/werner_sleeping_v1_transparent.png";
import wernerStationFishing from "./poses/werner_station_fishing_v1_transparent.png";
import wernerTobogganingBody from "./poses/werner_tobogganing_body_v2_transparent.png";
import wernerWaking from "./poses/werner_waking_v1_transparent.png";

/**
 * Authored illustration poses used inside sanctioned animated wrappers.
 *
 * These are not product moods. `Werner.tsx` retains the complete four-mood
 * public contract; this private vocabulary prevents wrappers from importing
 * pose files directly or substituting a semantically unrelated mood.
 *
 * `tobogganing` is the identity-preserving clean body derived from the
 * ChatGPT Image source (SPR-23). Only the body component is used — speed
 * streaks, snow puffs, and ground shadow from the source are separated into
 * code-native SVG/CSS in WernerTobogganSpinner.
 *
 * `stationFishing` (SPR-24) is the deterministic station body: an exact,
 * identity-preserving crop of canonical Werner with complete attached feet
 * and flippers, but no rod, line, hook, fish, snow, shadow, background, text,
 * or motion marks. It replaces the vector limb overlay (feet + flippers SVG)
 * that was misregistered against the raster silhouette.
 */
const AUTHORED_POSE = {
  duskGaze: wernerDuskGaze,
  headTilt: wernerHeadTilt,
  sleeping: wernerSleeping,
  stationFishing: wernerStationFishing,
  tobogganing: wernerTobogganingBody,
  waking: wernerWaking,
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
