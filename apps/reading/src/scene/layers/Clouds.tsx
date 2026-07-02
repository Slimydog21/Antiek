import { useEffect, useRef } from "react";

import { subscribeSceneClock, FROZEN_T } from "../useSceneClock";
import { cloudX, makeClouds, type CloudPuff } from "../field";
import { fieldSeed } from "../field";
import { moodAlpha, resolveToken } from "../palette";
import { moodKey, type SceneMood } from "../mood";
import { sceneLayerTransform } from "../../design/motion/sceneMotion";

/**
 * Clouds (SPR-04, milestone 2 — parallax cloud drift).
 *
 * A Canvas layer of soft radial blobs drifting in two parallax bands (far =
 * slow/high/faint, near = faster/lower). Painted every frame off the SINGLE
 * scene clock (subscribeSceneClock), NOT its own rAF — one heartbeat for the
 * whole scene. The cloud LAYOUT is deterministic (makeClouds(seed)); only the x
 * drift advances with time, so the same mood seed gives the same clouds.
 *
 * CANVAS vs CSS/WebGL (defensibility): clouds are few (CLOUD_COUNT=7) but each
 * is a soft radial gradient — cheap on Canvas, awkward to keep crisp + cheap as
 * pure CSS at this blur, and not worth a WebGL context for 7 blobs. Canvas 2D
 * is the right middle. See the Scene-level Canvas-vs-WebGL note.
 *
 * FREEZE: under reduced-motion subscribeSceneClock emits ONE frame at FROZEN_T
 * and never loops → a single static cloudscape, no running loop.
 *
 * COLOUR: pulled from design tokens via resolveToken (palette.ts) — no raw hex.
 */

export interface CloudsProps {
  mood: SceneMood;
  /** test seam: force reduced-motion (one static frame, no loop). */
  reducedMotion?: boolean;
}

export function Clouds({ mood, reducedMotion }: CloudsProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const seed = fieldSeed(moodKey(mood));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom / no-canvas env: the layer is simply blank.

    const puffs: CloudPuff[] = makeClouds(seed);
    const { cloud: cloudAlpha } = moodAlpha(mood);
    const cloudColor = resolveToken("cloud");
    const hazeColor = resolveToken("haze");

    const dpr = Math.min(
      typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1,
      2, // cap DPR at 2 — retina sharpness without 4× fill cost on hidpi.
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
      const drift = sceneLayerTransform("clouds", t, { reducedMotion });
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "source-over";
      for (const c of puffs) {
        const cx = cloudX(c, t, W) + drift.x * dpr;
        const cy = c.y * H + drift.y * dpr;
        const radius = c.scale * Math.min(W, H) * 0.22;
        if (radius <= 0) continue;
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
        // Token colours; alpha from the mood + per-cloud multiplier.
        grad.addColorStop(0, cloudColor);
        grad.addColorStop(0.55, hazeColor);
        grad.addColorStop(1, "transparent");
        ctx.globalAlpha = cloudAlpha * c.alpha;
        ctx.beginPath();
        ctx.ellipse(cx, cy, radius, radius * 0.6, 0, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };

    const onResize = () => {
      fit();
      draw(FROZEN_T); // repaint immediately on resize
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
    // mood seed + reducedMotion are the only meaningful deps; the canvas ref is
    // stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed, reducedMotion, mood.dayPart]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 h-full w-full"
      data-testid="clouds-layer"
      aria-hidden="true"
    />
  );
}

export default Clouds;
