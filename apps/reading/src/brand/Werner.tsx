import type { CSSProperties } from "react";

import "./werner/animated/animations.css";
import type { WernerMood } from "../design/tokens";

/**
 * Canonical Werner — the single source of truth for the penguin mark.
 *
 * One component. Two fidelities from the same geometry. Four moods only.
 * The rail calls it cute at 28 px; the hero surface sees the deadpan at 120 px.
 * Motion is CSS only and collapses under prefers-reduced-motion.
 *
 * Restraint is load-bearing: Werner appears in rail (idle), AI working (thinking),
 * blank states (empty), and core-action complete (celebrate). Nowhere else.
 * See brand/README.md.
 *
 * The static MOODS list and the dev-only runtime guard below are the mechanical
 * enforcement of the four-slot rule. Adding a fifth mood string will throw in
 * development before any visual regression or Storybook render can hide it.
 *
 * Key numbers + the one constraint each. viewBox 0-32. Bill apex y≈15.7,
 * 3.4u tall so it clears ~3px at 28px (a 2.3u bill smudged at rail size).
 * isCharacter ≥ 48px: wing/toe strokes alias below it. Idle sway 4.2s, head
 * tilt -6°: subtle enough not to read as "dancing". Four moods only; the
 * WernerMood union + the dev guard below enforce it. See brand/README.md.
 */

const MOODS = ["idle", "thinking", "empty", "celebrate"] as const;

type Props = {
  mood?: WernerMood;
  size?: number;
  label?: string;
  className?: string;
  // Positioning passthrough — animated wrappers (e.g. the toboggan spinner)
  // place the mark absolutely; merged after the intrinsic size box.
  style?: CSSProperties;
};

export default function Werner({
  mood = "idle",
  size = 28,
  label,
  className,
  style,
}: Props) {
  // Dev runtime guard — throws immediately on any string outside the four.
  // This is the mechanical half of U-02; the visual half lives in the rail
  // 28 px render and the CanonicalMoods story. A fifth mood cannot reach
  // production or even a Storybook build without this firing first.
  if (process.env.NODE_ENV !== "production" && mood && !(MOODS as readonly string[]).includes(mood)) {
    throw new Error(
      `Werner: invalid mood "${mood}". Only ${MOODS.join(", ")} are permitted. ` +
        "The four-slot restraint is non-negotiable per brand/README.md and U-02."
    );
  }

  const isCharacter = size >= 48; // mark fidelity below, character above
  const rootClass = mood === "idle" ? "werner-idle" : "";

  // Head tilt for thinking and empty carries the Herzog skepticism without caricature.
  const headRotate =
    mood === "thinking" || mood === "empty" ? "rotate(-6 16 11)" : "rotate(0 16 11)";

  // Celebrate lifts the whole and raises a flipper (reuses the one-shot keyframe).
  const bodyLift = mood === "celebrate" ? "translate(0 -1.2)" : "";

  return (
    <span
      role="img"
      aria-label={label || `Werner ${mood}`}
      className={className ? `inline-block align-middle ${className}` : "inline-block align-middle"}
      style={{ width: size, height: size, ...style }}
    >
      <svg
        viewBox="0 0 32 32"
        width={size}
        height={size}
        aria-hidden="true"
        style={{ display: "block" }}
      >
        <g className={rootClass} transform={bodyLift}>
          {/* Coat — rounded emperor silhouette, taller than wide. */}
          <ellipse
            cx="16"
            cy="17.8"
            rx="8.6"
            ry="10.3"
            fill="var(--werner-coat)"
          />

          {/* Belly — inset, catches the light. */}
          <ellipse
            cx="16"
            cy="19.2"
            rx="5.0"
            ry="7.2"
            fill="var(--werner-belly)"
          />

          {/* Head group — tilt lives here for personality in two moods. */}
          <g transform={headRotate}>
            <ellipse
              cx="16"
              cy="10.8"
              rx="5.8"
              ry="5.2"
              fill="var(--werner-coat)"
            />

            {/* Eyes — spaced for life, skeptical lid only in character fidelity. */}
            <circle cx="13.1" cy="10.0" r="1.05" fill="var(--werner-eye)" />
            <circle cx="18.9" cy="10.0" r="1.05" fill="var(--werner-eye)" />
            {isCharacter && (
              <path
                d="M12.4 9.25 Q13.1 9.0 13.75 9.25"
                stroke="var(--werner-eye)"
                strokeWidth="0.65"
                fill="none"
                strokeLinecap="round"
              />
            )}

            {/* Bill — the brand hook. Prominent high-contrast yellow at rail
                fidelity. See JSDoc derivations above for the 3.4-unit height. */}
            <path
              d="M14.4 12.3 L16.0 15.7 L17.6 12.3 Z"
              fill="var(--werner-bill)"
            />
          </g>

          {/* Feet — yellow anchors, splayed just enough to read as penguin. */}
          <ellipse
            cx="12.3"
            cy="28.4"
            rx="2.2"
            ry="0.85"
            fill="var(--werner-foot)"
          />
          <ellipse
            cx="19.7"
            cy="28.4"
            rx="2.2"
            ry="0.85"
            fill="var(--werner-foot)"
          />

          {/* Character fidelity only: subtle wing curve + toe hints. */}
          {isCharacter && (
            <>
              <path
                d="M8.3 15.2 Q7.0 19.8 8.6 23.4"
                stroke="var(--werner-coat)"
                strokeWidth="1.1"
                fill="none"
                opacity="0.18"
              />
              <path
                d="M11.1 28.9 L11.6 28.9"
                stroke="var(--werner-foot)"
                strokeWidth="0.6"
                opacity="0.45"
              />
              <path
                d="M12.3 28.9 L12.8 28.9"
                stroke="var(--werner-foot)"
                strokeWidth="0.6"
                opacity="0.45"
              />
              <path
                d="M19.5 28.9 L20.0 28.9"
                stroke="var(--werner-foot)"
                strokeWidth="0.6"
                opacity="0.45"
              />
              <path
                d="M20.7 28.9 L21.2 28.9"
                stroke="var(--werner-foot)"
                strokeWidth="0.6"
                opacity="0.45"
              />
            </>
          )}
        </g>

        {/* Thinking aurora dots — right-to-left pulse, reused from the
            existing restrained system. Positioned off the bill so the
            beat reads as consideration, not decoration. */}
        {mood === "thinking" && (
          <>
            <circle
              cx="23.4"
              cy="8.8"
              r="0.85"
              fill="var(--aurora)"
              className="werner-thinking-dot-1"
            />
            <circle
              cx="24.8"
              cy="9.6"
              r="0.85"
              fill="var(--aurora)"
              className="werner-thinking-dot-2"
            />
            <circle
              cx="25.9"
              cy="10.6"
              r="0.85"
              fill="var(--aurora)"
              className="werner-thinking-dot-3"
            />
            <circle
              cx="26.6"
              cy="11.8"
              r="0.85"
              fill="var(--aurora)"
              className="werner-thinking-dot-4"
            />
          </>
        )}

        {/* Celebrate one-shot: raised flipper + sparkle. The keyframe
            lives in the shared animations file so the motion stays
            consistent with the rest of the pose suite. */}
        {mood === "celebrate" && (
          <>
            <g className="werner-fish-flipper" transform="translate(1 -1)">
              <path
                d="M22.8 15.5 Q26.2 11.8 25.4 9.2 Q24.6 10.4 23.8 13.2 Z"
                fill="var(--werner-coat)"
              />
            </g>
            <g
              className="werner-fish-sparkle"
              transform="translate(25.2 8.4) scale(0.9)"
            >
              <path
                d="M0 -5.2 L1.0 -1.0 L5.2 0 L1.0 1.0 L0 5.2 L-1.0 1.0 L-5.2 0 L-1.0 -1.0 Z"
                fill="var(--sun)"
              />
            </g>
          </>
        )}
      </svg>
    </span>
  );
}

export type { WernerMood };