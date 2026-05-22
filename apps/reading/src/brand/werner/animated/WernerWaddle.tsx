import "./animations.css";

/**
 * Werner the penguin, waddling — route-navigation transition.
 *
 * Brand § 10: 3-frame loop (left-foot, both-feet, right-foot) over
 * 300ms total + 2° body rotation for the waddle bob. Use as a
 * sub-route transition between modes when the operator clicks G+I
 * / G+W / G+N — a quick "Werner is walking you over" beat.
 *
 * Default size 32 fits between the NavRail icons. The transition
 * helper that owns the "show Werner during nav" lifecycle lives in
 * `useWaddleTransition` (sibling file).
 */
type Props = { size?: number; label?: string };

export default function WernerWaddle({
  size = 32,
  label = "Navigating",
}: Props) {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-block align-middle"
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
        <g className="werner-waddle">
          {/* Body */}
          <ellipse cx="16" cy="17" rx="9" ry="11" fill="#0F1419" />
          <ellipse cx="16" cy="19" rx="5.5" ry="8" fill="#EEF1F6" />
          {/* Eyes — open + forward */}
          <circle cx="13" cy="13" r="1.4" fill="#0F1419" />
          <circle cx="19" cy="13" r="1.4" fill="#0F1419" />
          {/* Bill */}
          <path d="M14.5 16 L16 18 L17.5 16 Z" fill="#F5DF24" />
          {/* Feet — alternate up-cycle */}
          <ellipse
            cx="12.5"
            cy="29"
            rx="2.5"
            ry="1"
            fill="#F5DF24"
            className="werner-waddle-foot-l"
          />
          <ellipse
            cx="19.5"
            cy="29"
            rx="2.5"
            ry="1"
            fill="#F5DF24"
            className="werner-waddle-foot-r"
          />
        </g>
      </svg>
    </span>
  );
}
