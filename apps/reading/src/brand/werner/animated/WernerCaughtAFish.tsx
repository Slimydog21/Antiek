import "./animations.css";

/**
 * Werner the penguin, caught a fish — one-shot completion celebration.
 *
 * Brand § 10: flipper raise + sparkle scale 0 → 1 → 0 over 800ms.
 * No loop. Use for the "investigation complete" toast / banner.
 *
 * Default size 48 matches the LemonToast viewport item height + 8px.
 * One-shot CSS animations restart only on remount, so the
 * `key` prop should change per fire (e.g., per investigation id).
 */
type Props = { size?: number; label?: string };

export default function WernerCaughtAFish({
  size = 48,
  label = "Investigation complete",
}: Props) {
  return (
    <span
      role="img"
      aria-label={label}
      className="inline-block align-middle"
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden="true">
        {/* Body */}
        <ellipse cx="32" cy="34" rx="14" ry="18" fill="#0F1419" />
        <ellipse cx="32" cy="38" rx="9" ry="13" fill="#EEF1F6" />
        {/* Eyes — open + bright (happy) */}
        <circle cx="27" cy="28" r="1.8" fill="#0F1419" />
        <circle cx="37" cy="28" r="1.8" fill="#0F1419" />
        <circle cx="27.5" cy="27.4" r="0.6" fill="#EEF1F6" />
        <circle cx="37.5" cy="27.4" r="0.6" fill="#EEF1F6" />
        {/* Bill */}
        <path d="M29 32 L32 35 L35 32 Z" fill="#F5DF24" />
        {/* Feet */}
        <ellipse cx="26" cy="55" rx="3" ry="1.2" fill="#F5DF24" />
        <ellipse cx="38" cy="55" rx="3" ry="1.2" fill="#F5DF24" />
        {/* Raised flipper holding the fish */}
        <g className="werner-fish-flipper">
          <path
            d="M44 32 Q52 22 50 16 Q48 18 47 22 Q45 26 44 32 Z"
            fill="#0F1419"
          />
          {/* The fish */}
          <ellipse cx="51" cy="14" rx="5" ry="2.6" fill="#16C2C2" />
          <path
            d="M55 14 L58 12 L58 16 Z"
            fill="#16C2C2"
          />
          <circle cx="49" cy="13.5" r="0.6" fill="#EEF1F6" />
        </g>
        {/* Sparkle — eight-point star at the catch */}
        <g
          className="werner-fish-sparkle"
          transform="translate(54 16)"
        >
          <path
            d="M0 -6 L1.2 -1.2 L6 0 L1.2 1.2 L0 6 L-1.2 1.2 L-6 0 L-1.2 -1.2 Z"
            fill="#F5DF24"
          />
        </g>
      </svg>
    </span>
  );
}
