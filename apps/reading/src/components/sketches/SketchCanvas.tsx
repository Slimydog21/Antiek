import { useEffect, useRef } from "react";

import type { SketchBaseParams, SketchRender } from "./types";

export interface SketchCanvasProps<P extends SketchBaseParams = SketchBaseParams> {
  /** Pure sketch renderer. */
  render: SketchRender<P>;
  /** Sketch params (seed, knobs, mode). */
  params: P;
  /** CSS pixel width. Default 320. */
  width?: number;
  /** CSS pixel height. Default 200. */
  height?: number;
  /**
   * Force reduced-motion (tests / storybook). When omitted, reads
   * prefers-reduced-motion from the environment.
   */
  reducedMotion?: boolean;
  /**
   * When true (default) and reduced-motion is off, advance `params.t` via rAF.
   * Set false for a single static paint even when motion is allowed.
   */
  animate?: boolean;
  className?: string;
  /** Accessible label for the canvas. */
  "aria-label"?: string;
  /** data-testid for tests. */
  testId?: string;
}

function readPrefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * React canvas host for Processing-style sketches.
 *
 * Owns: DPR scaling, resize, rAF loop (gated by reduced-motion), cleanup.
 * Does NOT own: sketch logic — that stays in pure render(ctx, w, h, params).
 */
export function SketchCanvas<P extends SketchBaseParams>({
  render,
  params,
  width = 320,
  height = 200,
  reducedMotion: reducedMotionProp,
  animate = true,
  className,
  "aria-label": ariaLabel = "Generative sketch",
  testId = "sketch-canvas",
}: SketchCanvasProps<P>) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // Keep latest render/params in refs so the rAF loop does not re-subscribe
  // on every parent render (matches Snow/Clouds scene pattern).
  const renderRef = useRef(render);
  const paramsRef = useRef(params);
  renderRef.current = render;
  paramsRef.current = params;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom: blank layer, no crash.

    const reduced =
      reducedMotionProp ?? readPrefersReducedMotion();
    const dpr = Math.min(
      typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1,
      2,
    );

    const fit = () => {
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      // Draw in CSS-pixel space; the bitmap is DPR-scaled.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    fit();

    const paint = (t: number) => {
      const p = {
        ...paramsRef.current,
        t,
        reducedMotion: reduced,
      } as P;
      // Clear in device pixels then re-apply transform so sketches see CSS space.
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      renderRef.current(ctx, width, height, p);
    };

    // Always paint one frame immediately (static under reduced-motion).
    paint(paramsRef.current.t ?? 0);

    if (reduced || !animate) {
      // No rAF loop — house accessibility floor.
      return;
    }

    let raf = 0;
    let start = 0;
    const baseT = paramsRef.current.t ?? 0;
    const tick = (now: number) => {
      if (!start) start = now;
      paint(baseT + (now - start));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      if (raf) cancelAnimationFrame(raf);
    };
  }, [width, height, reducedMotionProp, animate, params.seed]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      data-testid={testId}
      role="img"
      aria-label={ariaLabel}
      width={width}
      height={height}
      style={{
        display: "block",
        width,
        height,
        maxWidth: "100%",
        borderRadius: 8,
      }}
    />
  );
}

export default SketchCanvas;
