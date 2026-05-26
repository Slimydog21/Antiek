import { useCallback, useEffect, useRef, useState } from "react";

import { durationMs } from "../../design/motion";

/**
 * useCelebrate — the one-shot trigger behind every signature delight beat
 * (U-05 M2).
 *
 * A beat is a brief, non-blocking flourish at a product's real payoff
 * moment (a research starts, a draft generates, a biography assembles, a
 * book opens). The shape is identical across all four: fire once, run for
 * at most the `slow` motion token, then clear itself. The visible half is
 * <CelebrateBurst>; this hook is the state half.
 *
 * Non-blocking is the load-bearing property: `celebrate()` only flips a
 * boolean and arms a timer — it never awaits, never gates the caller's
 * own state update or navigation. The payoff (the id, the draft, the
 * opened book) is already available; the beat just decorates it. Under
 * reduced-motion the <CelebrateBurst> render collapses to a static frame
 * (Werner's own animations.css fallback), so the hook needs no branch for
 * it — the timing is the same, only the pixels stop moving.
 *
 * Fires once per trigger: a second `celebrate()` while one is in flight
 * restarts the window rather than stacking, so a double-event can't queue
 * two penguins.
 */
export interface CelebrateState {
  /** True while the beat is in its window. Drives <CelebrateBurst>. */
  celebrating: boolean;
  /** Arm the beat. Non-blocking — returns immediately. */
  celebrate: () => void;
}

export function useCelebrate(): CelebrateState {
  const [celebrating, setCelebrating] = useState(false);
  const timer = useRef<number | null>(null);

  const clear = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const celebrate = useCallback(() => {
    clear();
    setCelebrating(true);
    // Auto-retire at the slow-token ceiling — Werner's celebrate one-shot
    // is 800 ms (== the slow token), so the boolean and the keyframe
    // finish together.
    timer.current = window.setTimeout(() => {
      setCelebrating(false);
      timer.current = null;
    }, durationMs.slow);
  }, [clear]);

  useEffect(() => clear, [clear]);

  return { celebrating, celebrate };
}
