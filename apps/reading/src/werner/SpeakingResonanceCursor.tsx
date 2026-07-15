import { useEffect, useRef } from "react";

import { useMouseFollow, type UseMouseFollowOptions } from "./useMouseFollow";
import "./speaking-resonance.css";

export interface SpeakingResonanceCursorProps {
  /** Disabled under reduced motion so the native cursor remains visible. */
  disabled?: boolean;
  /** Injectable clock for deterministic pointer-idle tests. */
  now?: UseMouseFollowOptions["now"];
}

/**
 * HTML-native listening microphone for canonical Speak routes.
 *
 * It is decorative cursor chrome only: no microphone permission, recording,
 * transcript/content read, navigation, networking, spend, or Werner control.
 */
export function SpeakingResonanceCursor({
  disabled = false,
  now,
}: SpeakingResonanceCursorProps) {
  const microphoneRef = useRef<HTMLSpanElement | null>(null);
  const follow = useMouseFollow({ disabled, now });

  useEffect(() => {
    const root = document.documentElement;
    if (!disabled) root.classList.add("werner-speaking-resonance-active");
    else root.classList.remove("werner-speaking-resonance-active");
    return () => root.classList.remove("werner-speaking-resonance-active");
  }, [disabled]);

  useEffect(() => {
    if (disabled) return;

    let raf = 0;
    const tick = () => {
      const microphone = microphoneRef.current;
      if (microphone) {
        const { live, pointerIdle, tabHidden } = follow.read();
        if (!live || tabHidden) {
          microphone.style.display = "none";
        } else {
          microphone.style.display = "block";
          microphone.style.left = `${live.x}px`;
          microphone.style.top = `${live.y}px`;
          microphone.classList.toggle(
            "speaking-resonance-cursor--idle",
            pointerIdle,
          );
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
      ref={microphoneRef}
      className="speaking-resonance-cursor"
      data-testid="speaking-resonance-cursor"
      aria-hidden="true"
    >
      <span className="speaking-resonance-cursor__grille" />
      <span className="speaking-resonance-cursor__signal" />
      <span className="speaking-resonance-cursor__stem" />
    </span>
  );
}

export default SpeakingResonanceCursor;
