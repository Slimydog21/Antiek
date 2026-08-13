/**
 * Synthesis wave (Processing-style seed sketch §12).
 *
 * Layered harmonic waves that "compose" into a single synthesis envelope —
 * the visual of multi-source claims resolving into one reading. Same seed →
 * same harmonics + phases. Under reduced-motion the envelope is a still
 * frame; with motion, `params.t` phase-shifts the carriers.
 *
 * Pure Canvas2D. No p5.js. Token colours only.
 */

import { accent, sun, sunLight, surface } from "../../design/tokens";
import { coerceSeed, makeRng } from "./seed";
import type { SketchBaseParams, SketchRender } from "./types";

const SKETCH_SALT = 0x5e11e5e1;

export interface SynthesisWaveParams extends SketchBaseParams {
  /** Number of carrier harmonics. Clamped to [2, 12]. Default 5. */
  harmonics?: number;
  /** Horizontal samples across the canvas. Clamped to [32, 512]. Default 160. */
  samples?: number;
  /** Amplitude scale in [0.2, 1]. Default 0.7. */
  amplitude?: number;
}

export interface Harmonic {
  /** Frequency multiplier (relative to fundamental). */
  freq: number;
  /** Amplitude weight in [0, 1]. */
  amp: number;
  /** Phase offset in radians. */
  phase: number;
  /** 0 = carrier, 1 = near-fundamental (for colour). */
  warmth: number;
}

/**
 * Pure harmonic set — no canvas. Deterministic given seed + knobs.
 */
export function layoutSynthesisWave(
  seed: string | number,
  harmonics = 5,
): Harmonic[] {
  const n = Math.max(2, Math.min(12, Math.floor(harmonics)));
  const rng = makeRng(coerceSeed(seed) ^ SKETCH_SALT);
  const out: Harmonic[] = [];
  for (let i = 0; i < n; i++) {
    out.push({
      freq: (i + 1) * rng.range(0.85, 1.25),
      amp: rng.range(0.25, 1) / (1 + i * 0.35),
      phase: rng.range(0, Math.PI * 2),
      warmth: 1 - i / Math.max(1, n - 1),
    });
  }
  return out;
}

/** Sample the composite wave y in [-1, 1] at normalised x in [0, 1]. */
export function sampleWave(
  harmonics: Harmonic[],
  x: number,
  phaseShift: number,
): number {
  let y = 0;
  let w = 0;
  for (const h of harmonics) {
    y += h.amp * Math.sin(x * Math.PI * 2 * h.freq + h.phase + phaseShift * h.freq);
    w += h.amp;
  }
  return w > 0 ? y / w : 0;
}

export const DEFAULT_SYNTHESIS_WAVE_PARAMS: SynthesisWaveParams = {
  seed: "antiek-synthesis-wave",
  harmonics: 5,
  samples: 160,
  amplitude: 0.7,
  t: 0,
  reducedMotion: false,
  mode: "night",
};

/**
 * Pure render. Mutates only the canvas context.
 * reducedMotion → frozen phase (t ignored).
 */
export const renderSynthesisWave: SketchRender<SynthesisWaveParams> = (
  ctx,
  width,
  height,
  params,
) => {
  const {
    seed,
    harmonics = 5,
    samples = 160,
    amplitude = 0.7,
    t = 0,
    reducedMotion = false,
    mode = "night",
  } = params;

  const hs = layoutSynthesisWave(seed, harmonics);
  const nSamples = Math.max(32, Math.min(512, Math.floor(samples)));
  const amp = Math.max(0.2, Math.min(1, amplitude));
  const palette = surface[mode];
  const bg = palette[2];
  const carrierColor = mode === "night" ? sunLight.base : sun.deep.day;
  const synthColor = mode === "night" ? sun.base : accent.aurora.day;
  const ghostColor = mode === "night" ? accent.aurora.night : accent.aurora.day;
  const ink = palette[8];
  const minDim = Math.min(width, height);
  const midY = height * 0.5;
  const ampPx = height * 0.32 * amp;

  // Phase advances under motion; frozen under reduced-motion.
  const phaseShift = reducedMotion ? 0 : (t / 1000) * 0.7;

  ctx.save();
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  // Horizontal guide (synthesis baseline).
  ctx.strokeStyle = ink;
  ctx.globalAlpha = 0.12;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, midY + 0.5);
  ctx.lineTo(width, midY + 0.5);
  ctx.stroke();
  ctx.globalAlpha = 1;

  // Ghost individual carriers (faint).
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (let hi = 0; hi < hs.length; hi++) {
    const h = hs[hi];
    ctx.strokeStyle = h.warmth > 0.5 ? carrierColor : ghostColor;
    ctx.globalAlpha = 0.1 + h.warmth * 0.12;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i <= nSamples; i++) {
      const x = i / nSamples;
      const y =
        midY +
        Math.sin(x * Math.PI * 2 * h.freq + h.phase + phaseShift * h.freq) *
          ampPx *
          h.amp;
      const px = x * width;
      if (i === 0) ctx.moveTo(px, y);
      else ctx.lineTo(px, y);
    }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  // Composite synthesis envelope (filled under-curve + stroke).
  const points: Array<{ x: number; y: number }> = [];
  for (let i = 0; i <= nSamples; i++) {
    const x = i / nSamples;
    const y = midY + sampleWave(hs, x, phaseShift) * ampPx;
    points.push({ x: x * width, y });
  }

  // Fill under the composite.
  ctx.beginPath();
  ctx.moveTo(points[0].x, midY);
  for (const p of points) ctx.lineTo(p.x, p.y);
  ctx.lineTo(points[points.length - 1].x, midY);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, midY - ampPx, 0, midY + ampPx);
  grad.addColorStop(0, withAlpha(synthColor, 0.28));
  grad.addColorStop(0.5, withAlpha(synthColor, 0.08));
  grad.addColorStop(1, withAlpha(ghostColor, 0.18));
  ctx.fillStyle = grad;
  ctx.fill();

  // Composite stroke.
  ctx.strokeStyle = synthColor;
  ctx.globalAlpha = 0.95;
  ctx.lineWidth = 2 * (minDim / 320);
  ctx.beginPath();
  for (let i = 0; i < points.length; i++) {
    if (i === 0) ctx.moveTo(points[i].x, points[i].y);
    else ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.stroke();
  ctx.globalAlpha = 1;

  // Sample ticks along the envelope (reads as "claims resolved").
  const tickEvery = Math.max(1, Math.floor(nSamples / 12));
  for (let i = 0; i <= nSamples; i += tickEvery) {
    const p = points[i];
    ctx.fillStyle = synthColor;
    ctx.globalAlpha = 0.55;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 2.2 * (minDim / 320), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

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

function withAlpha(hex: string, alpha: number): string {
  const a = Math.max(0, Math.min(1, alpha));
  if (hex.startsWith("rgba") || hex.startsWith("rgb")) return hex;
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
