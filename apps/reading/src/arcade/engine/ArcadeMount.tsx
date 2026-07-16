import { useEffect, useId, useLayoutEffect, useRef } from "react";

import { createArcadeLoop } from "./loop";
import { createSeededRng } from "./rng";
import type { Cartridge, InputState } from "./types";

export interface ArcadeMountProps {
  cartridge: Cartridge;
  width?: number;
  height?: number;
  seed?: number;
  reducedMotion?: boolean;
  /** Freeze simulation without re-initialising or tearing down the cartridge. */
  paused?: boolean;
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
  paused = false,
  className,
  testId = "arcade-mount",
}: ArcadeMountProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const bestRef = useRef(0);
  const loopRef = useRef<ReturnType<typeof createArcadeLoop> | null>(null);
  const clearInputRef = useRef<(() => void) | null>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const instructionsId = useId();

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
    const capturedPointers = new Set<number>();
    let loop: ReturnType<typeof createArcadeLoop> | null = null;

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
      if (
        [
          " ",
          "ArrowDown",
          "ArrowUp",
          "ArrowLeft",
          "ArrowRight",
          "Enter",
          "Escape",
          "q",
          "w",
        ].includes(e.key)
      ) {
        e.preventDefault();
      }
      if (pausedRef.current) return;
      const pressed = !keysDown.has(e.key);
      if (pressed) keysPressed.add(e.key);
      keysDown.add(e.key);
      if (reducedMotion && pressed) loop?.stepOnce(sample());
    };
    const onKeyUp = (e: KeyboardEvent) => {
      keysDown.delete(e.key);
    };
    const onPointerMove = (e: PointerEvent) => {
      if (pausedRef.current) return;
      const rect = canvas.getBoundingClientRect();
      const scaleX = rect.width > 0 ? width / rect.width : 1;
      const scaleY = rect.height > 0 ? height / rect.height : 1;
      pointer = {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY,
      };
    };
    const onPointerDown = (e: PointerEvent) => {
      if (pausedRef.current) return;
      canvas.focus();
      canvas.setPointerCapture(e.pointerId);
      capturedPointers.add(e.pointerId);
      pointerDown = true;
      pointerPressed = true;
      onPointerMove(e);
      if (reducedMotion) loop?.stepOnce(sample());
    };
    const onPointerUp = (e: PointerEvent) => {
      if (pausedRef.current) {
        pointerDown = false;
        pointerPressed = false;
        pointerReleased = false;
        if (canvas.hasPointerCapture(e.pointerId)) {
          canvas.releasePointerCapture(e.pointerId);
        }
        capturedPointers.delete(e.pointerId);
        return;
      }
      pointerDown = false;
      pointerReleased = true;
      if (canvas.hasPointerCapture(e.pointerId)) {
        canvas.releasePointerCapture(e.pointerId);
      }
      capturedPointers.delete(e.pointerId);
      if (reducedMotion) loop?.stepOnce(sample());
    };
    const onBlur = () => {
      keysDown.clear();
      keysPressed.clear();
      pointerDown = false;
    };
    clearInputRef.current = () => {
      keysDown.clear();
      keysPressed.clear();
      pointerDown = false;
      pointerPressed = false;
      pointerReleased = false;
      for (const pointerId of capturedPointers) {
        if (canvas.hasPointerCapture(pointerId)) {
          canvas.releasePointerCapture(pointerId);
        }
      }
      capturedPointers.clear();
    };

    canvas.addEventListener("keydown", onKeyDown);
    canvas.addEventListener("keyup", onKeyUp);
    canvas.addEventListener("blur", onBlur);
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
    loop = createArcadeLoop({
      cartridge,
      ctx,
      getInput: sample,
      getCtx2d: () => c2d,
      reducedMotion,
    });
    loopRef.current = loop;
    if (!pausedRef.current) loop.start();

    return () => {
      loop?.stop();
      if (loopRef.current === loop) loopRef.current = null;
      clearInputRef.current = null;
      cartridge.teardown();
      for (const pointerId of capturedPointers) {
        if (canvas.hasPointerCapture(pointerId)) {
          canvas.releasePointerCapture(pointerId);
        }
      }
      capturedPointers.clear();
      canvas.removeEventListener("keydown", onKeyDown);
      canvas.removeEventListener("keyup", onKeyUp);
      canvas.removeEventListener("blur", onBlur);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
    };
  }, [cartridge, width, height, seed, reducedMotion]);

  useLayoutEffect(() => {
    const loop = loopRef.current;
    if (!loop) return;
    if (paused) {
      clearInputRef.current?.();
      loop.stop();
    } else {
      loop.start();
    }
  }, [paused]);

  return (
    <>
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className={className}
        data-testid={testId}
        data-paused={paused ? "true" : "false"}
        role="application"
        aria-disabled={paused || undefined}
        tabIndex={0}
        aria-label={cartridge.meta.title}
        aria-describedby={instructionsId}
        style={{
          display: "block",
          width,
          height,
          maxWidth: "100%",
          touchAction: "none",
          borderRadius: 8,
          background: "var(--card-soft)",
        }}
      />
      <span id={instructionsId} className="sr-only">
        Focus the game, then use Space or Enter to start. Arrow keys control Ice
        Fishing; Left and Right control Clam Catcher. Pointer or keyboard
        controls Paperclip Zombies. Escape exits.
      </span>
    </>
  );
}
