import { useEffect, useRef } from "react";

import { createArcadeLoop } from "./loop";
import { createSeededRng } from "./rng";
import type { Cartridge, InputState } from "./types";

export interface ArcadeMountProps {
  cartridge: Cartridge;
  width?: number;
  height?: number;
  seed?: number;
  reducedMotion?: boolean;
  className?: string;
  /** data-testid for shell / wait-host assertions */
  testId?: string;
}

/**
 * Mount a cartridge on a canvas. Opt-in only — parent decides when to show.
 * Tears down on unmount (I4: never leaves a running loop behind).
 */
export function ArcadeMount({
  cartridge,
  width = 360,
  height = 240,
  seed = 1,
  reducedMotion = false,
  className,
  testId = "arcade-mount",
}: ArcadeMountProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const bestRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const c2d = canvas.getContext("2d");
    if (!c2d) return;

    const keysDown = new Set<string>();
    const keysPressed = new Set<string>();
    let pointer: { x: number; y: number } | null = null;
    let pointerDown = false;
    let pointerPressed = false;
    let pointerReleased = false;

    const sample = (): InputState => {
      const snap: InputState = {
        pointer,
        pointerDown,
        pointerPressed,
        pointerReleased,
        keysDown: new Set(keysDown),
        keysPressed: new Set(keysPressed),
      };
      keysPressed.clear();
      pointerPressed = false;
      pointerReleased = false;
      return snap;
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (!keysDown.has(e.key)) keysPressed.add(e.key);
      keysDown.add(e.key);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      keysDown.delete(e.key);
    };
    const onPointerMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    };
    const onPointerDown = (e: PointerEvent) => {
      canvas.setPointerCapture(e.pointerId);
      pointerDown = true;
      pointerPressed = true;
      onPointerMove(e);
    };
    const onPointerUp = (e: PointerEvent) => {
      pointerDown = false;
      pointerReleased = true;
      if (canvas.hasPointerCapture(e.pointerId)) {
        canvas.releasePointerCapture(e.pointerId);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);

    const ctx = {
      width,
      height,
      rng: createSeededRng(seed),
      saveBestScore: (score: number) => {
        if (score > bestRef.current) bestRef.current = score;
      },
      readBestScore: () => bestRef.current,
    };

    cartridge.init(ctx);
    const loop = createArcadeLoop({
      cartridge,
      ctx,
      getInput: sample,
      getCtx2d: () => c2d,
      reducedMotion,
    });
    loop.start();

    return () => {
      loop.stop();
      cartridge.teardown();
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
    };
  }, [cartridge, width, height, seed, reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className={className}
      data-testid={testId}
      role="img"
      aria-label={cartridge.meta.title}
      style={{
        display: "block",
        width,
        height,
        maxWidth: "100%",
        touchAction: "none",
        borderRadius: 8,
        background: "var(--color-bg-soft, #f3f1ea)",
      }}
    />
  );
}
