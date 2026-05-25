import "./animations.css";
import Werner from "../../Werner";

/**
 * Werner the penguin, caught a fish — one-shot completion celebration.
 *
 * Brand § 10: flipper raise + sparkle scale 0 → 1 → 0 over 800ms.
 * No loop. Use for the "investigation complete" toast / banner.
 *
 * Default size 48 matches the LemonToast viewport item height + 8px.
 * One-shot CSS animations restart only on remount, so the
 * `key` prop should change per fire (e.g., per investigation id).
 *
 * Core mark delegated to <Werner mood="celebrate" /> + --werner-* tokens
 * for any remaining accents. No more parallel geometry fork.
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
      {/* Core mark now single-source from canonical at celebrate fidelity.
          The fish flipper + sparkle chrome remain pose-specific overlays
          positioned to sit on the delegated Werner. */}
      <Werner mood="celebrate" size={size} />
      {/* Pose chrome overlays — minimal absolute SVGs for fish + sparkle only.
          The penguin body itself is fully delegated; no geometry duplication. */}
      <svg
        viewBox="0 0 64 64"
        width={size}
        height={size}
        style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}
        aria-hidden="true"
      >
        <g className="werner-fish-flipper" transform="translate(12 -4) scale(0.55)">
          <path d="M44 32 Q52 22 50 16 Q48 18 47 22 Q45 26 44 32 Z" fill="var(--werner-coat)" />
          <ellipse cx="51" cy="14" rx="5" ry="2.6" fill="#16C2C2" />
          <path d="M55 14 L58 12 L58 16 Z" fill="#16C2C2" />
          <circle cx="49" cy="13.5" r="0.6" fill="#EEF1F6" />
        </g>
        <g className="werner-fish-sparkle" transform="translate(22 -6) scale(0.45)">
          <path d="M0 -6 L1.2 -1.2 L6 0 L1.2 1.2 L0 6 L-1.2 1.2 L-6 0 L-1.2 -1.2 Z" fill="var(--werner-bill)" />
        </g>
      </svg>
    </span>
  );
}
