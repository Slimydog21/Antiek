/**
 * Map Flipbook-feel scenery clicks to product routes.
 *
 * Pure — unit tests drive this without AppShell. Hover stays ambient;
 * only click navigates. Unknown ids return null (no product action).
 */

import type { SceneHotspotId } from "./interactiveRegions";

export type SceneHotspotProductAction = {
  route: string;
  /** Werner experience to emit alongside navigation (if any). */
  wernerExperience: "highlight" | null;
};

/**
 * Product action for a scenery hotspot activation.
 * @returns null when the hotspot is ambient-only (no navigation).
 */
export function productActionForSceneHotspot(
  id: SceneHotspotId,
  kind: "hover" | "click",
): SceneHotspotProductAction | null {
  if (kind !== "click") return null;
  switch (id) {
    case "igloo-ridge":
      // Werner's igloo → arcade mini-games (opt-in cabinet).
      return { route: "/arcade", wernerExperience: "highlight" };
    case "horizon-journey":
      // Horizon path → research door (the journey of inquiry).
      return { route: "/", wernerExperience: "highlight" };
    case "peak-left":
      // Reserved for shell-launch honest click proof (ambient-only).
      return null;
    case "peak-right":
      // Right ridge → library / reading door.
      return { route: "/library", wernerExperience: "highlight" };
    case "sky-aurora":
      // Aurora sky → project home (warm orientation front door).
      return { route: "/home", wernerExperience: "highlight" };
    default: {
      const _exhaustive: never = id;
      return _exhaustive;
    }
  }
}
