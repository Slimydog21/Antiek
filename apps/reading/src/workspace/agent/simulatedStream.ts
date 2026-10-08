// SIMULATED STREAM: /thought-partner returns whole text (app.py:7218-7256). Replaced by SSE when SPR-B lands.
/**
 * simulatedStream.ts — renders a whole reply progressively, ~24 characters
 * per animation frame, so the thread's caret and status row behave as they
 * will under SSE. The pane's status row says "simulated stream" out loud
 * (AgentThread.tsx) whenever the transport kind is "whole"; this comment is
 * not the only place the simulation is named.
 */
export const CHARS_PER_FRAME = 24;

export interface SimulateStreamOptions {
  reducedMotion?: boolean;
  /** Emit the whole text once, synchronously (tests; reduced motion). */
  immediate?: boolean;
}

/** Returns a cancel function. `onChunk(sofar, done)` is called with the
 *  growing prefix; the final call has done === true. */
export function simulateStream(
  text: string,
  onChunk: (sofar: string, done: boolean) => void,
  opts: SimulateStreamOptions = {},
): () => void {
  if (opts.immediate || opts.reducedMotion || text.length <= CHARS_PER_FRAME) {
    onChunk(text, true);
    return () => {};
  }
  let at = 0;
  let cancelled = false;
  let handle: number | ReturnType<typeof setTimeout> | null = null;
  const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame : null;
  const schedule = (fn: () => void) => {
    handle = raf ? raf(() => fn()) : setTimeout(fn, 16);
  };
  const tick = () => {
    if (cancelled) return;
    at = Math.min(text.length, at + CHARS_PER_FRAME);
    const done = at >= text.length;
    onChunk(text.slice(0, at), done);
    if (!done) schedule(tick);
  };
  schedule(tick);
  return () => {
    cancelled = true;
    if (handle === null) return;
    if (raf && typeof cancelAnimationFrame === "function") cancelAnimationFrame(handle as number);
    else clearTimeout(handle as ReturnType<typeof setTimeout>);
  };
}
