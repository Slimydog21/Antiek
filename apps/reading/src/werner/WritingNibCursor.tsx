import { useEffect, useRef } from "react";

import { useMouseFollow, type UseMouseFollowOptions } from "./useMouseFollow";
import "./writing-nib.css";

export interface WritingNibCursorProps {
  /** Disabled under reduced motion so the native cursor remains visible. */
  disabled?: boolean;
  /** Injectable clock for deterministic pointer-idle tests. */
  now?: UseMouseFollowOptions["now"];
}

/**
 * HTML-native fountain-pen cursor for Write/Create routes.
 *
 * The generated scriptorium is design evidence only. This instrument follows
 * pointer coordinates, captures no events, reads no document content, and has
 * no authority over Werner, navigation, networking, or spend.
 */
export function WritingNibCursor({
  disabled = false,
  now,
}: WritingNibCursorProps) {
  const nibRef = useRef<HTMLSpanElement | null>(null);
  const follow = useMouseFollow({ disabled, now });

  useEffect(() => {
    const root = document.documentElement;
    if (!disabled) root.classList.add("werner-writing-nib-active");
    else root.classList.remove("werner-writing-nib-active");
    return () => root.classList.remove("werner-writing-nib-active");
  }, [disabled]);

  useEffect(() => {
    if (disabled) return;

    let raf = 0;
    const tick = () => {
      const nib = nibRef.current;
      if (nib) {
        const { live, pointerIdle, tabHidden } = follow.read();
        if (!live || tabHidden) {
          nib.style.display = "none";
        } else {
          nib.style.display = "block";
          nib.style.left = `${live.x}px`;
          nib.style.top = `${live.y}px`;
          nib.classList.toggle("writing-nib-cursor--idle", pointerIdle);
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
      ref={nibRef}
      className="writing-nib-cursor"
      data-testid="writing-nib-cursor"
      aria-hidden="true"
    >
      <span className="writing-nib-cursor__shoulder" />
      <span className="writing-nib-cursor__breather" />
      <span className="writing-nib-cursor__slit" />
    </span>
  );
}

export default WritingNibCursor;
