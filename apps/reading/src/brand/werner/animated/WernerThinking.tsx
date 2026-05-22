import "./animations.css";

/**
 * Werner the penguin, thinking — used as the AISidecar "thinking…"
 * state. Brand § 10: four aurora thought-dots pulse opacity 0.5 ↔ 1.0
 * in sequence right-to-left, 1.2s cycle. Same colour as the LemonTag
 * aurora variant so the pulse reads as "AI is working" across the
 * whole product surface.
 *
 * Sizes target 24 / 40 / 64; 40 is the default (sidecar header).
 */
type Props = { size?: number; label?: string };

export default function WernerThinking({
  size = 40,
  label = "AI is thinking",
}: Props) {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-flex items-center gap-2 align-middle"
    >
      <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
        {/* Werner head tilted slightly (curious). */}
        <ellipse cx="16" cy="17" rx="9" ry="11" fill="#0F1419" />
        <ellipse cx="16" cy="19" rx="5.5" ry="8" fill="#EEF1F6" />
        <circle cx="13" cy="13" r="1.4" fill="#0F1419" />
        <circle cx="19" cy="13" r="1.4" fill="#0F1419" />
        <path d="M14.5 16 L16 18 L17.5 16 Z" fill="#F5DF24" />
        <ellipse cx="12.5" cy="29" rx="2.5" ry="1" fill="#F5DF24" />
        <ellipse cx="19.5" cy="29" rx="2.5" ry="1" fill="#F5DF24" />
      </svg>
      {/* Four pulsing aurora dots; rightmost lights first so the
          motion reads right-to-left toward Werner's bill. */}
      <span className="inline-flex items-center gap-1.5">
        <span
          className="block werner-thinking-dot-1 rounded-full"
          style={{
            width: size * 0.16,
            height: size * 0.16,
            background: "#16C2C2",
          }}
          aria-hidden="true"
        />
        <span
          className="block werner-thinking-dot-2 rounded-full"
          style={{
            width: size * 0.16,
            height: size * 0.16,
            background: "#16C2C2",
          }}
          aria-hidden="true"
        />
        <span
          className="block werner-thinking-dot-3 rounded-full"
          style={{
            width: size * 0.16,
            height: size * 0.16,
            background: "#16C2C2",
          }}
          aria-hidden="true"
        />
        <span
          className="block werner-thinking-dot-4 rounded-full"
          style={{
            width: size * 0.16,
            height: size * 0.16,
            background: "#16C2C2",
          }}
          aria-hidden="true"
        />
      </span>
    </span>
  );
}
