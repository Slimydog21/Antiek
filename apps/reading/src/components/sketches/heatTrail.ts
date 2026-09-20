/**
 * Attention heat trail (Processing-style seed sketch §12).
 *
 * A seeded path of attention foci with decaying heat blobs + a connecting
 * trail — the visual of "where the eye (or the model) lingered". Same seed →
 * same foci and trail. Under reduced-motion the trail is fully drawn and
 * static; with motion, `params.t` advances a head along the path.
 *
 * Pure Canvas2D. No p5.js. Token colours only.
 */

import { accent, sun, sunLight, surface } from "../../design/tokens";
import { coerceSeed, makeRng } from "./seed";
import type { SketchBaseParams, SketchRender } from "./types";

const SKETCH_SALT = 0x8ea77e11;

export interface HeatTrailParams extends SketchBaseParams {
  /** Number of attention foci. Clamped to [3, 32]. Default 9. */
  focusCount?: number;
  /** Trail curvature / wander in [0, 1]. Default 0.55. */
  wander?: number;
}

export interface HeatFocus {
  /** Normalised x in [0, 1]. */
  x: number;
  /** Normalised y in [0, 1]. */
  y: number;
  /** Relative heat intensity in [0, 1]. */
  intensity: number;
  /** Blob radius scale in [0, 1]. */
  radius: number;
}

/**
 * Pure focus generator — no canvas. Deterministic given seed + knobs.
 * Foci form a wandering polyline suitable for a heat trail.
 */
export function layoutHeatTrail(
  seed: string | number,
  focusCount = 9,
  wander = 0.55,
): HeatFocus[] {
  const n = Math.max(3, Math.min(32, Math.floor(focusCount)));
  const w = Math.max(0, Math.min(1, wander));
  const rng = makeRng(coerceSeed(seed) ^ SKETCH_SALT);

  const foci: HeatFocus[] = [];
  // Start near a side, meander toward the opposite side.
  let x = rng.range(0.08, 0.28);
  let y = rng.range(0.2, 0.8);
  const targetX = rng.range(0.72, 0.94);
  const targetY = rng.range(0.15, 0.85);

  for (let i = 0; i < n; i++) {
    const t = i / Math.max(1, n - 1);
    // Bias toward target with wander noise.
    const pullX = (targetX - x) * (0.18 + t * 0.22);
    const pullY = (targetY - y) * (0.18 + t * 0.22);
    x = Math.max(0.05, Math.min(0.95, x + pullX + rng.range(-w * 0.12, w * 0.12)));
    y = Math.max(0.08, Math.min(0.92, y + pullY + rng.range(-w * 0.18, w * 0.18)));
    // Heat peaks mid-trail (attention crest), softer at ends.
    const crest = 1 - Math.abs(t - 0.55) * 1.4;
    foci.push({
      x,
      y,
      intensity: Math.max(0.2, Math.min(1, crest * rng.range(0.7, 1))),
      radius: rng.range(0.4, 1),
    });
  }
  return foci;
}

export const DEFAULT_HEAT_TRAIL_PARAMS: HeatTrailParams = {
  seed: "antiek-heat-trail",
  focusCount: 9,
  wander: 0.55,
  t: 0,
  reducedMotion: false,
  mode: "night",
};

/**
 * Pure render. Mutates only the canvas context.
 * reducedMotion → full trail, no head animation.
 */
export const renderHeatTrail: SketchRender<HeatTrailParams> = (
  ctx,
  width,
  height,
  params,
) => {
  const {
    seed,
    focusCount = 9,
    wander = 0.55,
    t = 0,
    reducedMotion = false,
    mode = "night",
  } = params;

  const foci = layoutHeatTrail(seed, focusCount, wander);
  const palette = surface[mode];
  const bg = palette[2];
  const trailColor = mode === "night" ? sunLight.base : sun.deep.day;
  const hotColor = mode === "night" ? sun.base : accent.emperor.day;
  const coolColor = mode === "night" ? accent.aurora.night : accent.aurora.day;
  const ink = palette[8];
  const minDim = Math.min(width, height);

  // Progress along the trail: full when reduced-motion; otherwise cycles.
  const progress = reducedMotion
    ? 1
    : ((t / 1000) * 0.15) % 1.15; // slight overshoot so head rests
  const headIndex = Math.min(foci.length - 1, progress * (foci.length - 1));
  const headFloor = Math.floor(headIndex);
  const headFrac = headIndex - headFloor;

  ctx.save();
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  // Soft heat field (radial blobs under the trail).
  for (let i = 0; i < foci.length; i++) {
    const f = foci[i];
    // Under motion, foci past the head are dimmer (not-yet-attended).
    const reveal = reducedMotion ? 1 : Math.max(0, Math.min(1, headIndex - i + 1));
    if (reveal <= 0) continue;
    const px = f.x * width;
    const py = f.y * height;
    const r = (18 + f.radius * 36) * (minDim / 320);
    const g = ctx.createRadialGradient(px, py, 0, px, py, r);
    const a = f.intensity * 0.45 * reveal;
    g.addColorStop(0, withAlpha(hotColor, a));
    g.addColorStop(0.45, withAlpha(trailColor, a * 0.45));
    g.addColorStop(1, withAlpha(coolColor, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fill();
  }

  // Connecting trail polyline (up to head).
  const visibleCount = reducedMotion
    ? foci.length
    : Math.max(1, Math.min(foci.length, headFloor + 1));
  if (visibleCount >= 2) {
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    // Outer glow stroke.
    ctx.strokeStyle = trailColor;
    ctx.globalAlpha = 0.22;
    ctx.lineWidth = 6 * (minDim / 320);
    strokeTrail(ctx, foci, width, height, visibleCount, headFrac, reducedMotion);
    // Core stroke.
    ctx.globalAlpha = 0.85;
    ctx.lineWidth = 1.6 * (minDim / 320);
    ctx.strokeStyle = hotColor;
    strokeTrail(ctx, foci, width, height, visibleCount, headFrac, reducedMotion);
    ctx.globalAlpha = 1;
  }

  // Foci dots.
  for (let i = 0; i < visibleCount; i++) {
    const f = foci[i];
    const px = f.x * width;
    const py = f.y * height;
    const r = (2 + f.intensity * 3.2) * (minDim / 320);
    ctx.fillStyle = i === headFloor && !reducedMotion ? hotColor : coolColor;
    ctx.globalAlpha = 0.55 + f.intensity * 0.45;
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  // Animated head cursor (skipped under reduced-motion).
  if (!reducedMotion && foci.length > 0) {
    const a = foci[headFloor];
    const b = foci[Math.min(foci.length - 1, headFloor + 1)];
    const hx = (a.x + (b.x - a.x) * headFrac) * width;
    const hy = (a.y + (b.y - a.y) * headFrac) * height;
    const hr = 4.5 * (minDim / 320);
    ctx.fillStyle = hotColor;
    ctx.globalAlpha = 0.95;
    ctx.beginPath();
    ctx.arc(hx, hy, hr, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 0.25;
    ctx.beginPath();
    ctx.arc(hx, hy, hr * 2.6, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  // Provenance fingerprint.
  const fingerprint = (coerceSeed(seed) >>> 0).toString(16).padStart(8, "0");
  ctx.fillStyle = ink;
  ctx.globalAlpha = 0.35;
  ctx.font = `${Math.max(8, minDim * 0.028)}px "JetBrains Mono", ui-monospace, monospace`;
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.fillText(fingerprint.slice(0, 8), width - 6, height - 4);
  ctx.globalAlpha = 1;
  ctx.restore();
};

function strokeTrail(
  ctx: CanvasRenderingContext2D,
  foci: HeatFocus[],
  width: number,
  height: number,
  visibleCount: number,
  headFrac: number,
  reducedMotion: boolean,
): void {
  ctx.beginPath();
  ctx.moveTo(foci[0].x * width, foci[0].y * height);
  const last = Math.min(visibleCount, foci.length);
  for (let i = 1; i < last; i++) {
    ctx.lineTo(foci[i].x * width, foci[i].y * height);
  }
  // Partial segment toward next focus when animating.
  if (!reducedMotion && last < foci.length && headFrac > 0) {
    const a = foci[last - 1];
    const b = foci[last];
    ctx.lineTo(
      (a.x + (b.x - a.x) * headFrac) * width,
      (a.y + (b.y - a.y) * headFrac) * height,
    );
  }
  ctx.stroke();
}

/** Apply an alpha to a #rrggbb (or already-rgba) colour string. */
function withAlpha(hex: string, alpha: number): string {
  const a = Math.max(0, Math.min(1, alpha));
  if (hex.startsWith("rgba") || hex.startsWith("rgb")) {
    // Already composite — fall back to a simple rgba black-ish veil is wrong;
    // parse is overkill: return as-is with globalAlpha preferred by caller.
    return hex;
  }
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((c) => c + c)
          .join("")
      : h.slice(0, 6);
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a.toFixed(3)})`;
}
