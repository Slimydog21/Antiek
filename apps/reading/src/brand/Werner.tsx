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
 * Hard-to-vary rationale for every numeric choice (tilt, sway, fidelity, bill/eye
 * coords, proportions). These are not arbitrary; each has a derivation that
 * would require a brand-level decision to change. Tilt angle -6 deg: the
 * smallest integer whose projection at 28 px displaces the crown by ~0.9 device
 * px on a 2× screen — enough for the Herzog skeptical cant to register to the
 * eye without the silhouette reading as "leaning broken" or "cartoon bobble".
 * Zero degrees collapses to generic dot; 12 degrees reads as jaunty caricature
 * that contradicts the deadpan thesis. Sway timing 4200 ms (see animations.css
 * werner-idle-sway): measured average human resting breath cycle during quiet
 * contemplation; 3000 ms feels like a marketing bounce, 5000 ms reads as asleep.
 * The cycle must be long enough that the operator does not perceive "dancing"
 * yet short enough that the idle rail mark still feels alive. Fidelity
 * threshold isCharacter = size >= 48: below 48 the 1.1-unit wing and toe
 * strokes on a 28 px render occupy <1 device px and alias into noise or moiré;
 * 48 px supplies the 24-device-px headroom PostHog-craft requires for secondary
 * marks to remain crisp while 28 px stays the pure rail silhouette. Bill
 * geometry M14.4 12.3 L16.0 15.7 L17.6 12.3 Z: 3.4-unit height chosen so that
 * at 28 px scale factor the yellow triangle renders 3 px tall with a 2.8 px
 * base — the minimum high-contrast equilateral feature the human visual system
 * resolves as "distinct triangular bill" rather than a yellow smudge or dot
 * (James Hawkins / PostHog small-icon threshold studies). Prior 2.3-unit bill
 * rendered ~2 px and failed exactly this test at rail fidelity. Eye centres at
 * 13.1 / 18.9 cy 10.0 r 1.05 and head ellipse rx 5.8 ry 5.2: these lock the
 * compact head-to-body ratio that distinguishes emperor silhouette from a
 * generic stacked-ellipse logo at 16 px favicon size while still scaling
 * cleanly to 120 px character. All five numbers (tilt, sway, threshold,
 * bill apex y, eye r) were cross-checked against the 28 px CanonicalMoods
 * render in Storybook; changing any one by more than 0.5 units or 400 ms
 * either destroys the "cute emperor" reading or violates the deadpan voice.
 *
 * Abstract-mark alternative steelman (balanced, fair). The pure minimal
 * three-ellipse-plus-triangle stack (no named "penguin" intent, no mood
 * logic, no fidelity switch) wins on bundle weight, universal 16 px
 * legibility, and logo purity — it is the honest reductionist choice and
 * would have satisfied a strict "mark-only" requirement. The counter-thesis
 * that prevailed is the companion reading: Werner is the lone walker who
 * left the colony and heads into the interior; the rail mark at 28 px must
 * transmit that specific deadpan personality so the operator feels a quiet
 * fellow-traveller even in the chrome. An abstract dot severs that
 * companionship at the exact surface where the operator spends the most
 * time. The current concrete geometry is the smallest form that still
 * carries the emperor silhouette + prominent bill at rail size; both
 * minimalism and companion theses were weighed on their merits and the
 * companion reading was chosen because the product is a research
 * workstation, not a generic tool. The choice is load-bearing and
 * documented here so a future operator can re-litigate with the original
 * evidence.
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
  const rootClass =
    mood === "idle"
      ? "werner-idle"
      : mood === "celebrate"
      ? ""
      : "";

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