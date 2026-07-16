import { useEffect, useRef } from "react";

import { useMouseFollow, type UseMouseFollowOptions } from "./useMouseFollow";
import "./brass-balance.css";

export interface BrassBalanceCursorProps {
  /** Disabled under reduced motion so the native cursor remains visible. */
  disabled?: boolean;
  /** Injectable clock for deterministic pointer-idle tests. */
  now?: UseMouseFollowOptions["now"];
}

/**
 * HTML-native brass-balance cursor for /pricing.
 *
 * A small weighing-scale rendered with pure HTML/CSS: fulcrum, beam, two
 * pans on chains, and a support post. The beam tilts when the pointer is
 * idle (the pans settle under their own weight) and levels when active
 * (measurement in progress). Instrument reads live/pointerIdle/tabHidden
 * only — no penguin state, no movement authority, no network reads.
 */
export function BrassBalanceCursor({
  disabled = false,
  now,
}: BrassBalanceCursorProps) {
  const cursorRef = useRef<HTMLSpanElement | null>(null);
  const follow = useMouseFollow({ disabled, now });

  useEffect(() => {
    const root = document.documentElement;
    if (!disabled) root.classList.add("werner-brass-balance-active");
    else {
      root.classList.remove("werner-brass-balance-active");
      root.classList.remove("werner-brass-balance-ready");
    }
    return () => {
      root.classList.remove("werner-brass-balance-active");
      root.classList.remove("werner-brass-balance-ready");
    };
  }, [disabled]);

  useEffect(() => {
    if (disabled) return;

    let raf = 0;
    const tick = () => {
      const el = cursorRef.current;
      if (el) {
        const { live, pointerIdle, tabHidden } = follow.read();
        if (!live || tabHidden) {
          el.style.display = "none";
        } else {
          document.documentElement.classList.add("werner-brass-balance-ready");
          el.style.display = "block";
          el.style.left = `${live.x}px`;
          el.style.top = `${live.y}px`;
          el.classList.toggle("brass-balance-cursor--idle", pointerIdle);
          el.classList.toggle("brass-balance-cursor--active", !pointerIdle);
        }
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [disabled, follow]);

  if (disabled) return null;

  return (
    <span
      ref={cursorRef}
      className="brass-balance-cursor"
      data-testid="brass-balance-cursor"
      aria-hidden="true"
    >
      <span className="brass-balance-cursor__pivot" />
      <span className="brass-balance-cursor__beam" />
      <span className="brass-balance-cursor__post" />
      <span className="brass-balance-cursor__chain brass-balance-cursor__chain--left" />
      <span className="brass-balance-cursor__chain brass-balance-cursor__chain--right" />
      <span className="brass-balance-cursor__pan brass-balance-cursor__pan--left" />
      <span className="brass-balance-cursor__pan brass-balance-cursor__pan--right" />
    </span>
  );
}

export default BrassBalanceCursor;
