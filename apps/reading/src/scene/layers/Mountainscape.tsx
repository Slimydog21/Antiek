import { useMemo } from "react";

import type { SceneMood } from "../mood";
import { moodKey } from "../mood";
import { makeRidge, type RidgePoint, ridgePathD } from "../peaks";
import { fieldSeed } from "../field";
import { atmosphereFor } from "../palette";

/**
 * Mountainscape (ALC SPR-05 M4 — parallax-ready depth) — NEW.
 *
 * A dedicated DEPTH layer: ≥3 seeded ridge PLANES (far / mid / near) with an
 * atmospheric HAZE veil between them, composed so distance reads through
 * value + saturation RECESSION, not just overlap. This is the static depth
 * substrate SPR-06 lights up for parallax — every plane exposes a TYPED
 * TRANSFORM SEAM (see `PlaneSeam`) that SPR-06 drives; this sprint animates
 * NOTHING and adds NO @keyframes.
 *
 * ─── DEPTH MODEL: value/saturation recession (the documented decision) ──────
 * Aerial perspective says distant terrain loses CONTRAST and SATURATION and
 * shifts toward the sky/haze colour. We encode that as three planes:
 *
 *   plane │ role  │ value (token)        │ haze veil over it │ vertical anchor
 *   ──────┼───────┼──────────────────────┼───────────────────┼────────────────
 *   0     │ far   │ lightest, most recede │ HEAVIEST (0.42)   │ highest (0.30)
 *   1     │ mid   │ mid value             │ light (0.20)      │ middle (0.52)
 *   2     │ near  │ darkest, full contrast│ none (0.00)       │ lowest (0.74)
 *
 * The far plane sits highest + lightest + most-hazed → it RECEDES; the near
 * plane is lowest, darkest, un-veiled → it ADVANCES. The haze colour is the
 * per-dayPart `--scene-haze-*` token, so recession tracks the time of day.
 *
 * WHY A SEPARATE LAYER (not folded into ProceduralSky): ProceduralSky owns the
 * SKY + the distant backdrop ridge; Mountainscape owns the FOREGROUND ground
 * planes the penguin journeys across, with their own parallax depths. Keeping
 * them separate gives SPR-06 two independently-driveable parallax surfaces
 * (sky-backdrop vs foreground terrain) and keeps each file's geometry single-
 * owner (no two layers fighting over the same ridge bands).
 *
 * DETERMINISM: every plane's ridge comes from pure `makeRidge(seed ^ salt)`;
 * the seed is `fieldSeed(moodKey)`. Same mood → byte-identical planes. No
 * Date.now / Math.random / rAF. Memoized on the seed.
 *
 * COLOUR DISCIPLINE: peak fills are Tailwind token classes (fill-*); the haze
 * veil is a `var(--scene-haze-*)` token. ZERO raw hex (token-lint).
 */

/**
 * The TYPED TRANSFORM SEAM each plane exposes for SPR-06 parallax.
 *
 * SPR-06 drives a plane by passing a `transform` (and optionally a small
 * `opacity` delta for atmospheric crossfade between dayPart anchors). The seam
 * is intentionally transform/opacity ONLY — the two GPU-cheap, layout-free
 * properties — so parallax never thrashes layout and the motion guard never
 * trips (no keyframes; SPR-06 animates these props via its clock, not CSS).
 *
 * `depth` is the plane's parallax STRENGTH (0 = locked to the backdrop, 1 =
 * moves most). Far = small depth, near = large depth — SPR-06 multiplies its
 * pointer/scroll signal by `depth` to get each plane's shift, exactly as
 * Peaks.tsx already does for the backdrop ridge.
 */
export interface PlaneSeam {
  /** transform applied to the plane group (translate only; SPR-06 fills this). */
  transform?: string;
  /** opacity multiplier for atmospheric crossfade (SPR-06; default 1). */
  opacity?: number;
}

/** One depth plane's static design: role, value class, haze weight, anchor,
 *  parallax depth, and the ridge shape parameters. */
interface PlaneDef {
  role: "far" | "mid" | "near";
  /** Tailwind fill class per dayPart family (day | twilight | night). */
  fill: { day: string; dawn: string; dusk: string; night: string };
  /** haze-veil opacity over this plane (aerial recession; far = heaviest). */
  haze: number;
  /** vertical anchor (fraction of canvas height the plane's base sits). */
  anchor: number;
  /** parallax strength 0..1 — the seam multiplier SPR-06 uses. */
  depth: number;
  /** ridge generation parameters + a seed salt distinct from ProceduralSky. */
  seedSalt: number;
  ridge: { points: number; roughness: number; base: number; amp: number };
}

/** The three planes, far → near. Salts are DISTINCT from peaks.ts PEAK_BANDS
 *  seedOffsets (0x11/0x22/0x33) so the foreground terrain is a different ridge
 *  than the backdrop — they don't visually echo each other. */
const PLANES: PlaneDef[] = [
  {
    role: "far",
    fill: {
      day: "fill-glacial-1",
      dawn: "fill-glacial-2",
      dusk: "fill-charcoal-2",
      night: "fill-charcoal-1",
    },
    haze: 0.42,
    anchor: 0.3,
    depth: 0.3,
    seedSalt: 0xa1,
    ridge: { points: 17, roughness: 0.45, base: 0.16, amp: 0.26 },
  },
  {
    role: "mid",
    fill: {
      day: "fill-glacial-2",
      dawn: "fill-shadow-1",
      dusk: "fill-charcoal-1",
      night: "fill-space-2",
    },
    haze: 0.2,
    anchor: 0.52,
    depth: 0.6,
    seedSalt: 0xb2,
    ridge: { points: 17, roughness: 0.6, base: 0.2, amp: 0.4 },
  },
  {
    role: "near",
    fill: {
      day: "fill-shadow-1",
      dawn: "fill-shadow-2",
      dusk: "fill-space-1",
      night: "fill-space-1",
    },
    haze: 0,
    anchor: 0.74,
    depth: 1,
    seedSalt: 0xc3,
    ridge: { points: 17, roughness: 0.72, base: 0.26, amp: 0.52 },
  },
];

/** The parallax depths each plane exposes — SPR-06 reads this to scale its
 *  per-plane shift (far moves least, near most). Exported so SPR-06 + tests can
 *  assert the recession ordering without reaching into the component. */
export const PLANE_DEPTHS: number[] = PLANES.map((p) => p.depth);

export interface MountainscapeProps {
  mood: SceneMood;
  /**
   * Per-plane transform/opacity seams, far → near (index-aligned with PLANES).
   * SPR-06 supplies these to drive parallax; omitted ⇒ a static composed frame
   * (this sprint always omits them).
   */
  seams?: PlaneSeam[];
}

export function Mountainscape({ mood, seams }: MountainscapeProps) {
  const key = moodKey(mood);
  const seed = fieldSeed(key);
  const haze = atmosphereFor(mood.dayPart).haze;

  // Pure, seeded, memoized — byte-stable per mood.
  const planes = useMemo(
    () =>
      PLANES.map((p) => ({
        def: p,
        points: makeRidge((seed ^ p.seedSalt) >>> 0, p.ridge) as RidgePoint[],
      })),
    [seed],
  );

  const fillFor = (def: PlaneDef): string => def.fill[mood.dayPart];

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      data-testid="mountainscape-layer"
      data-mood={key}
      data-daypart={mood.dayPart}
      aria-hidden="true"
    >
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        focusable="false"
      >
        {planes.map(({ def, points }, i) => {
          const seam = seams?.[i];
          const d = ridgePathD(points, def.anchor * 18);
          return (
            <g
              key={def.role}
              data-plane={def.role}
              data-depth={def.depth}
              style={{
                transform: seam?.transform,
                opacity: seam?.opacity,
                // hint the compositor this group is transform-animated (SPR-06)
                // without animating it now.
                willChange: seam?.transform ? "transform" : undefined,
              }}
            >
              <path d={d} className={fillFor(def)} />
              {def.haze > 0 && (
                <path d={d} data-plane-haze={def.role} fill={haze} opacity={def.haze} />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default Mountainscape;
