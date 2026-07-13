import { useEffect, useRef } from "react";

import { useMouseFollow, type UseMouseFollowOptions } from "./useMouseFollow";
import "./research-lens.css";

export interface ResearchLensCursorProps {
  /** Disabled under reduced motion so the native cursor remains visible. */
  disabled?: boolean;
  /** Injectable clock for deterministic pointer-idle tests. */
  now?: UseMouseFollowOptions["now"];
}

/**
 * HTML-native research lens cursor.
 *
 * The generated observatory frame is design evidence; this is the real
 * interaction layer. It follows the live pointer by imperative DOM writes,
 * never captures input, never reads document content, and never moves Werner.
 */
export function ResearchLensCursor({
  disabled = false,
  now,
}: ResearchLensCursorProps) {
  const lensRef = useRef<HTMLSpanElement | null>(null);
  const follow = useMouseFollow({ disabled, now });

  useEffect(() => {
    if (disabled) return;

    let raf = 0;
    const tick = () => {
      const lens = lensRef.current;
      if (lens) {
        const { live, pointerIdle, tabHidden } = follow.read();
        if (!live || tabHidden) {
          lens.style.display = "none";
        } else {
          lens.style.display = "block";
          lens.style.left = `${live.x}px`;
          lens.style.top = `${live.y}px`;
          lens.classList.toggle("research-lens-cursor--idle", pointerIdle);
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
      ref={lensRef}
      className="research-lens-cursor"
      data-testid="research-lens-cursor"
      aria-hidden="true"
    >
      <span className="research-lens-cursor__glass" />
    </span>
  );
}

export default ResearchLensCursor;
