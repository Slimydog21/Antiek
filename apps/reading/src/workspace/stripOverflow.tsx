/**
 * stripOverflow.tsx — what a horizontally scrolling tab strip has out of
 * view, for the cues that say so (lane A stage B3, defects 1 and 8): an edge
 * fade on each side the tabs continue, and a count of the tabs scrolled out
 * of view. Shared by the document strip (left pane) and the agent strip
 * (right pane), so both panes speak one overflow language.
 *
 * Measured from the DOM (the scroller's scroll box and each tab's rect), on
 * mount, on scroll, on a resize of the scroller, and whenever one of the
 * caller's `deps` changes (the tab set, or the labels that size the tabs).
 * A tab counts as out of view when its midpoint is.
 */
import { useCallback, useLayoutEffect, useState, type RefObject } from "react";

export interface StripOverflow {
  /** Tabs continue before the scrolled-to start. */
  start: boolean;
  /** Tabs continue after the visible end. */
  end: boolean;
  /** Tabs whose midpoint is scrolled out of view, before / after. */
  hiddenBefore: number;
  hiddenAfter: number;
}

export const NO_OVERFLOW: StripOverflow = { start: false, end: false, hiddenBefore: 0, hiddenAfter: 0 };

/** The overflow of `scroller` now (tabs are its `[role='tab']` descendants). */
export function measureStripOverflow(scroller: HTMLElement): StripOverflow {
  const { scrollLeft, clientWidth, scrollWidth } = scroller;
  if (scrollWidth <= clientWidth + 1) return NO_OVERFLOW;
  const box = scroller.getBoundingClientRect();
  let hiddenBefore = 0;
  let hiddenAfter = 0;
  for (const tab of scroller.querySelectorAll<HTMLElement>("[role='tab']")) {
    const r = tab.getBoundingClientRect();
    if (r.width === 0) continue;
    const mid = (r.left + r.right) / 2;
    if (mid < box.left) hiddenBefore += 1;
    else if (mid > box.left + clientWidth) hiddenAfter += 1;
  }
  return {
    start: scrollLeft > 1,
    end: scrollLeft + clientWidth < scrollWidth - 1,
    hiddenBefore,
    hiddenAfter,
  };
}

function same(a: StripOverflow, b: StripOverflow): boolean {
  return a.start === b.start && a.end === b.end && a.hiddenBefore === b.hiddenBefore && a.hiddenAfter === b.hiddenAfter;
}

/** Live overflow of the scroller behind `ref`; a change in `deps` re-measures
 *  (keep them stable references: they are effect dependencies). */
export function useStripOverflow(ref: RefObject<HTMLElement | null>, deps: readonly unknown[]): StripOverflow {
  const [state, setState] = useState<StripOverflow>(NO_OVERFLOW);
  const update = useCallback(() => {
    const el = ref.current;
    const next = el ? measureStripOverflow(el) : NO_OVERFLOW;
    setState((prev) => (same(prev, next) ? prev : next));
  }, [ref]);

  useLayoutEffect(() => {
    update();
    // `deps` are the caller's re-measure triggers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [update, ...deps]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    ro?.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      ro?.disconnect();
    };
  }, [ref, update]);

  return state;
}

/**
 * The edge fades over a scroller: a short gradient into the strip's surface
 * on each side the tabs continue. Decoration only (aria-hidden, no pointer
 * events); the counts and the overflow menu carry the information.
 * `surface` is the gradient's `from-` colour pair, the strip's own surface.
 */
export function EdgeFades({
  overflow,
  surface = "from-ice-1 dark:from-charcoal-1",
}: {
  overflow: StripOverflow;
  surface?: string;
}) {
  return (
    <>
      {overflow.start ? (
        <span
          aria-hidden="true"
          data-edge-fade="start"
          className={`pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r to-transparent ${surface}`}
        />
      ) : null}
      {overflow.end ? (
        <span
          aria-hidden="true"
          data-edge-fade="end"
          className={`pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l to-transparent ${surface}`}
        />
      ) : null}
    </>
  );
}

/**
 * A vertical wheel over a strip scrolls it sideways (the strips hide their
 * scrollbar: a classic scrollbar would eat the 28 px row on Linux). A
 * horizontal gesture (trackpad) is left to the browser.
 */
export function scrollStripOnWheel(e: { currentTarget: HTMLElement; deltaX: number; deltaY: number }): void {
  const el = e.currentTarget;
  if (Math.abs(e.deltaY) <= Math.abs(e.deltaX) || el.scrollWidth <= el.clientWidth) return;
  el.scrollLeft += e.deltaY;
}
