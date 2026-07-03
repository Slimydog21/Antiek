import { motion } from "../tokens";

export type SceneMotionLayer = "peaks" | "clouds" | "snow" | "krea";

export interface SceneLayerTransform {
  x: number;
  y: number;
  opacity: number;
}

export interface CrossfadeTransition {
  fromOpacity: number;
  toOpacity: number;
  startedAtMs: number;
  durationMs: number;
}

export const CROSSFADE = {
  durationMs: 1200,
  reducedDurationMs: 0,
  paintedOpacity: 0.82,
  easeIn: motion.easing.enter,
  easeOut: motion.easing.standard,
} as const;

export const PARALLAX = {
  peaksCoefficient: 0.28,
  cloudCoefficient: 0.42,
  snowCoefficient: 0.68,
} as const;

export const DRIFT = {
  peaks: { xAmplitudePx: 2.4, yAmplitudePx: 1.2, xPeriodMs: 41_000, yPeriodMs: 47_000 },
  clouds: { xAmplitudePx: 10, yAmplitudePx: 1.5, xPeriodMs: 53_000, yPeriodMs: 59_000 },
  snow: { xAmplitudePx: 4, yAmplitudePx: 2, xPeriodMs: 31_000, yPeriodMs: 37_000 },
  krea: { xAmplitudePx: 1.6, yAmplitudePx: 0.8, xPeriodMs: 61_000, yPeriodMs: 67_000 },
} satisfies Record<
  SceneMotionLayer,
  {
    xAmplitudePx: number;
    yAmplitudePx: number;
    xPeriodMs: number;
    yPeriodMs: number;
  }
>;

export function sceneLayerTransform(
  layer: SceneMotionLayer,
  clockMs: number,
  opts: { reducedMotion?: boolean } = {},
): SceneLayerTransform {
  if (opts.reducedMotion) return { x: 0, y: 0, opacity: 1 };
  const spec = DRIFT[layer];
  return {
    x: wave(clockMs, spec.xPeriodMs, spec.xAmplitudePx),
    y: wave(clockMs + spec.yPeriodMs / 4, spec.yPeriodMs, spec.yAmplitudePx),
    opacity: 1,
  };
}

export function sceneParallaxPx(
  layer: Exclude<SceneMotionLayer, "krea">,
  pointerNormal: { x: number; y: number },
  maxPx: number,
  opts: { reducedMotion?: boolean } = {},
): { x: number; y: number } {
  if (opts.reducedMotion) return { x: 0, y: 0 };
  const coefficient =
    layer === "peaks"
      ? PARALLAX.peaksCoefficient
      : layer === "clouds"
        ? PARALLAX.cloudCoefficient
        : PARALLAX.snowCoefficient;
  return {
    x: pointerNormal.x * maxPx * coefficient,
    y: pointerNormal.y * maxPx * coefficient,
  };
}

export function createCrossfadeTransition(
  startedAtMs: number,
  opts: {
    fromOpacity?: number;
    toOpacity?: number;
    reducedMotion?: boolean;
  } = {},
): CrossfadeTransition {
  const toOpacity = opts.toOpacity ?? CROSSFADE.paintedOpacity;
  return {
    fromOpacity: opts.reducedMotion ? toOpacity : (opts.fromOpacity ?? 0),
    toOpacity,
    startedAtMs,
    durationMs: opts.reducedMotion ? CROSSFADE.reducedDurationMs : CROSSFADE.durationMs,
  };
}

export function crossfadeOpacity(
  transition: CrossfadeTransition,
  clockMs: number,
): number {
  if (transition.durationMs <= 0) return transition.toOpacity;
  const progress = clamp01((clockMs - transition.startedAtMs) / transition.durationMs);
  const eased = easeInOut(progress);
  return lerp(transition.fromOpacity, transition.toOpacity, eased);
}

export function retargetCrossfade(
  transition: CrossfadeTransition,
  clockMs: number,
  nextOpacity: number,
  opts: { reducedMotion?: boolean } = {},
): CrossfadeTransition {
  const currentOpacity = opts.reducedMotion
    ? nextOpacity
    : crossfadeOpacity(transition, clockMs);
  return createCrossfadeTransition(clockMs, {
    fromOpacity: currentOpacity,
    toOpacity: nextOpacity,
    reducedMotion: opts.reducedMotion,
  });
}

export function crossfadeMaxSlopePerMs(transition: CrossfadeTransition): number {
  if (transition.durationMs <= 0) return Number.POSITIVE_INFINITY;
  return Math.abs(transition.toOpacity - transition.fromOpacity) / transition.durationMs;
}

function wave(clockMs: number, periodMs: number, amplitudePx: number): number {
  return Number((Math.sin((clockMs / periodMs) * Math.PI * 2) * amplitudePx).toFixed(4));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}
