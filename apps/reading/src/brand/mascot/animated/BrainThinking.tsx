import "./animations.css";
import BrainMascot from "../../BrainMascot";

/**
 * Brain the mascot, thinking — used as the AISidecar "thinking…"
 * state. Brand § 10: four aurora thought-dots pulse opacity 0.5 ↔ 1.0
 * in sequence right-to-left, 1.2s cycle. Same colour as the LemonTag
 * aurora variant so the pulse reads as "AI is working" across the
 * whole product surface.
 *
 * Sizes target 24 / 40 / 64; 40 is the default (sidecar header).
 *
 * Core mark delegated to <BrainMascot mood="thinking" /> + --mascot-* tokens
 * for any remaining accents. No more parallel geometry fork.
 */
type Props = { size?: number; label?: string };

export default function BrainThinking({
  size = 40,
  label = "AI is thinking",
}: Props) {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-flex items-center gap-2 align-middle"
    >
      {/* The canonical thinking pose carries the semantic state; the four
          external aurora dots make ongoing work legible even at 20–24 px. */}
      <BrainMascot mood="thinking" size={size} />
      <span className="inline-flex items-center gap-1.5">
        <span
          className="block mascot-thinking-dot-1 rounded-full"
          style={{
            width: size * 0.16,
            height: size * 0.16,
            background: "var(--aurora)",
          }}
          aria-hidden="true"
        />
        <span
          className="block mascot-thinking-dot-2 rounded-full"
          style={{
            width: size * 0.16,
            height: size * 0.16,
            background: "var(--aurora)",
          }}
          aria-hidden="true"
        />
        <span
          className="block mascot-thinking-dot-3 rounded-full"
          style={{
            width: size * 0.16,
            height: size * 0.16,
            background: "var(--aurora)",
          }}
          aria-hidden="true"
        />
        <span
          className="block mascot-thinking-dot-4 rounded-full"
          style={{
            width: size * 0.16,
            height: size * 0.16,
            background: "var(--aurora)",
          }}
          aria-hidden="true"
        />
      </span>
    </span>
  );
}
