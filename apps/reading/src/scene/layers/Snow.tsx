import { useEffect, useRef } from "react";

import { subscribeSceneClock, FROZEN_T } from "../useSceneClock";
import {
  fieldSeed,
  makeSnow,
  snowAt,
  type SnowParticle,
} from "../field";
import { moodAlpha, resolveToken } from "../palette";
import { moodKey, type SceneMood } from "../mood";
import { sceneLayerTransform } from "../../design/motion/sceneMotion";

/**
 * Snow (SPR-04, milestone 2 — wind-driven snow particles).
 *
 * The Herzog Antarctic motif — an always-on flurry. A Canvas layer of
 * SNOW_COUNT flakes falling + drifting with a wind term, painted every frame
 * off the SINGLE scene clock (subscribeSceneClock), NOT its own loop. The flake
 * SET is deterministic (makeSnow(seed)); positions advance purely with time
 * (snowAt), so the same seed → the same frame N (the determinism test).
 *
 * BUDGET: SNOW_COUNT = 140 flakes (see field.ts rationale). Each flake is a
 * single arc fill; 140 fills/frame is negligible. Tuned down from 250 so the
 * flurry never whites-out the glass content above it (text-contrast safety).
 *
 * WIND: a gentle constant drift (WIND) blows flakes to one side, so the snow
 * reads as weather, not a vertical curtain. Bounded + deterministic.
 *
 * FREEZE: under reduced-motion, one static frame at FROZEN_T, no loop.
 * COLOUR: the flake colour is the lightest design token (palette.ts) — no hex.
 */

/** Constant horizontal wind (field-widths/sec scale inside snowAt). A light
 *  breeze: enough to slant the fall, not a storm. */
const WIND = 1.4;

export interface SnowProps {
  mood: SceneMood;
  /** test seam: force reduced-motion (one static frame, no loop). */
  reducedMotion?: boolean;
}

export function Snow({ mood, reducedMotion }: SnowProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const seed = fieldSeed(moodKey(mood));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom / no-canvas: blank layer, no crash.

    const flakes: SnowParticle[] = makeSnow(seed);
    const { snow: snowAlpha } = moodAlpha(mood);
    const flakeColor = resolveToken("flake");

    const dpr = Math.min(
      typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1,
      2,
    );
    const fit = () => {
      const w = canvas.clientWidth || 1;
      const h = canvas.clientHeight || 1;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    };
    fit();

    const draw = (t: number) => {
      const W = canvas.width;
      const H = canvas.height;
      const drift = sceneLayerTransform("snow", t, { reducedMotion });
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = flakeColor;
      ctx.globalAlpha = snowAlpha;
      for (const f of flakes) {
        const { x, y } = snowAt(f, t, W, H, WIND);
        const r = f.r * dpr;
        ctx.beginPath();
        ctx.arc(x + drift.x * dpr, y + drift.y * dpr, r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };

    const onResize = () => {
      fit();
      draw(FROZEN_T);
    };
    if (typeof window !== "undefined") {
      window.addEventListener("resize", onResize);
    }

    const unsub = subscribeSceneClock((t) => draw(t), { reducedMotion });

    return () => {
      unsub();
      if (typeof window !== "undefined") {
        window.removeEventListener("resize", onResize);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed, reducedMotion, mood.dayPart]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 h-full w-full"
      data-testid="snow-layer"
      aria-hidden="true"
    />
  );
}

export default Snow;
