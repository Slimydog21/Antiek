/**
 * Fixed-timestep arcade loop.
 *
 * One rAF per mount (not a global second clock for the whole app — whimsy
 * rigClock is not yet in-tree). Pauses when the document is hidden. Clamps
 * frame dt so a stall cannot fling simulation. Injectable `now` for tests.
 */

import type { Cartridge, GameContext, InputState } from "./types";

export const FIXED_DT_SEC = 1 / 60;
export const MAX_FRAME_SEC = 0.05;
export const MAX_SUBSTEPS = 5;

export interface LoopHost {
  now: () => number;
  requestFrame: (cb: FrameRequestCallback) => number;
  cancelFrame: (id: number) => void;
  isHidden: () => boolean;
}

export function defaultLoopHost(): LoopHost {
  return {
    now: () =>
      typeof performance !== "undefined" ? performance.now() : Date.now(),
    requestFrame: (cb) => requestAnimationFrame(cb),
    cancelFrame: (id) => cancelAnimationFrame(id),
    isHidden: () => (typeof document !== "undefined" ? document.hidden : false),
  };
}

export interface ArcadeLoop {
  start: () => void;
  stop: () => void;
  /** Drive one fixed step with synthetic input (headless tests). */
  stepOnce: (input: InputState) => void;
  isRunning: () => boolean;
}

export interface CreateLoopOptions {
  cartridge: Cartridge;
  ctx: GameContext;
  getInput: () => InputState;
  getCtx2d: () => CanvasRenderingContext2D | null;
  host?: LoopHost;
  /** When true, skip render (pure simulation tests). */
  headless?: boolean;
  /** Reduced motion: still allow opt-in static frame, no continuous sim. */
  reducedMotion?: boolean;
}

export function createArcadeLoop(options: CreateLoopOptions): ArcadeLoop {
  const host = options.host ?? defaultLoopHost();
  let running = false;
  let frameId: number | null = null;
  let lastMs = 0;
  let accumulator = 0;
  const emptyInput: InputState = {
    pointer: null,
    pointerDown: false,
    pointerPressed: false,
    pointerReleased: false,
    keysDown: new Set(),
    keysPressed: new Set(),
  };

  const tick = (ms: number) => {
    if (!running) return;
    if (host.isHidden() || options.reducedMotion) {
      lastMs = ms;
      frameId = host.requestFrame(tick);
      return;
    }
    const raw = (ms - lastMs) / 1000;
    lastMs = ms;
    const frame = Math.min(Math.max(raw, 0), MAX_FRAME_SEC);
    accumulator += frame;
    let input: InputState | null = null;
    let steps = 0;
    while (accumulator >= FIXED_DT_SEC && steps < MAX_SUBSTEPS) {
      // Sample only when a simulation step will consume the input. Sampling on
      // a zero-step render frame would clear producer-owned press edges before
      // the game could observe them.
      input ??= options.getInput();
      const stepInput =
        steps === 0
          ? input
          : {
              ...input,
              pointerPressed: false,
              pointerReleased: false,
              keysPressed: new Set<string>(),
            };
      // A catch-up frame may run several fixed steps, but a physical press is
      // an edge and therefore belongs to the first step only.
      options.cartridge.update(FIXED_DT_SEC, stepInput, options.ctx);
      accumulator -= FIXED_DT_SEC;
      steps += 1;
    }
    if (!options.headless) {
      const c2d = options.getCtx2d();
      if (c2d) options.cartridge.render(c2d, options.ctx);
    }
    // Clear edge flags after consume by mutating through getInput producer;
    // producers rebuild pressed sets each sample — see ArcadeMount.
    frameId = host.requestFrame(tick);
  };

  return {
    start() {
      if (running) return;
      running = true;
      lastMs = host.now();
      accumulator = 0;
      if (options.reducedMotion) {
        // One still frame only.
        const c2d = options.getCtx2d();
        if (c2d && !options.headless) {
          options.cartridge.render(c2d, options.ctx);
        }
        return;
      }
      frameId = host.requestFrame(tick);
    },
    stop() {
      running = false;
      if (frameId !== null) {
        host.cancelFrame(frameId);
        frameId = null;
      }
    },
    stepOnce(input: InputState) {
      options.cartridge.update(FIXED_DT_SEC, input ?? emptyInput, options.ctx);
      if (!options.headless) {
        const c2d = options.getCtx2d();
        if (c2d) options.cartridge.render(c2d, options.ctx);
      }
    },
    isRunning: () => running,
  };
}
