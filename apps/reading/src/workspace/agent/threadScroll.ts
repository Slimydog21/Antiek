/**
 * threadScroll.ts — follow-the-tail with a yielding auto-scroll (SPR-07
 * M3; refs patterns 13/16, posthog carry-overs 12–14).
 *
 *   following  the thread snaps to its end as content grows;
 *   unfollow   the user took the scroll position (pointerdown, touchstart,
 *              an upward wheel, an upward scroll away from the end);
 *   re-follow  only a downward scroll back into the near-end band (80 px)
 *              or the "Jump to latest" button.
 */
import { useCallback, useLayoutEffect, useRef, useState, type RefObject } from "react";

export const NEAR_END_PX = 80;

export interface ScrollMetrics {
  scrollHeight: number;
  scrollTop: number;
  clientHeight: number;
}

export function nearEnd(m: ScrollMetrics): boolean {
  return m.scrollHeight - m.scrollTop - m.clientHeight < NEAR_END_PX;
}

export type FollowEvent =
  | { type: "pointerdown" }
  | { type: "touchstart" }
  | { type: "wheel"; deltaY: number }
  | { type: "scroll"; direction: "up" | "down"; metrics: ScrollMetrics }
  | { type: "jump" };

export function reduceFollow(following: boolean, e: FollowEvent): boolean {
  switch (e.type) {
    case "pointerdown":
    case "touchstart":
      return false;
    case "wheel":
      return e.deltaY < 0 ? false : following;
    case "scroll":
      if (e.direction === "down") return nearEnd(e.metrics) ? true : following;
      return nearEnd(e.metrics) ? following : false;
    case "jump":
      return true;
  }
}

/** Wires the reducer to a scroll container; snaps to the end in a layout
 *  effect while following, so growing content never flashes above the fold. */
export function useFollowTail(ref: RefObject<HTMLElement | null>, contentKey: unknown) {
  const [following, setFollowing] = useState(true);
  const lastTop = useRef(0);
  const dispatch = useCallback((e: FollowEvent) => setFollowing((f) => reduceFollow(f, e)), []);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !following) return;
    el.scrollTop = el.scrollHeight;
    lastTop.current = el.scrollTop;
  }, [ref, following, contentKey]);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const direction = el.scrollTop >= lastTop.current ? "down" : "up";
    lastTop.current = el.scrollTop;
    dispatch({ type: "scroll", direction, metrics: { scrollHeight: el.scrollHeight, scrollTop: el.scrollTop, clientHeight: el.clientHeight } });
  }, [ref, dispatch]);

  const jump = useCallback(() => {
    dispatch({ type: "jump" });
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [ref, dispatch]);

  return {
    following,
    jump,
    handlers: {
      onScroll,
      onPointerDown: () => dispatch({ type: "pointerdown" }),
      onTouchStart: () => dispatch({ type: "touchstart" }),
      onWheel: (e: { deltaY: number }) => dispatch({ type: "wheel", deltaY: e.deltaY }),
    },
  };
}
