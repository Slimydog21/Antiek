/**
 * IglooMark (SPR-06 M4) — the home control's mark.
 *
 * The operator asked for the static top-left penguin (the home button) to
 * become an IGLOO. Werner LIVES in the igloo, so the home door reads as
 * "go back to where Werner lives" — the brand's front step — rather than a
 * second penguin competing with the one autonomous penguin that roams the
 * app (PenguinMascot). One penguin, one igloo: the igloo is the fixed home,
 * the penguin is the wandering project companion.
 *
 * Drawn inline in the Werner idiom, not rastered like the four <Werner>
 * poses: a mark this geometric (dome + brick courses + arched door) reads
 * crisp as pure vector at the 28px rail size AND scales to the hero sizes
 * without the alpha-cut fuss the photographic penguin needs. Lemon-UI
 * weight = 2px ink strokes (stroke-ink, the brand outline) on the
 * sun-yellow button behind it; the door glows sun so the eye reads "lit,
 * someone's home". No raw hex — every fill/stroke is a palette token
 * (fill-ice-0 / fill-sun / stroke-ink), so the lint:tokens gate stays green.
 *
 * Purely presentational: aria-hidden, no role. The semantics (link/button
 * role, aria-label, focus ring) live on the control that wraps it
 * (NavRail's home button), exactly as <Werner> is wrapped today.
 */
type Props = { size?: number; className?: string };

export default function IglooMark({ size = 28, className }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {/* Snow dome — a half-disc sitting on the ground line. */}
      <path
        d="M3 17 A9 9 0 0 1 21 17 Z"
        className="fill-ice-0 stroke-ink"
        strokeWidth={2}
        strokeLinejoin="round"
      />
      {/* Brick courses — two arcs echoing the dome so it reads as packed
          snow blocks, not a plain hill. Stroke-only, no fill. */}
      <path
        d="M5 13.2 A7.4 7.4 0 0 1 19 13.2"
        className="stroke-ink"
        strokeWidth={1.4}
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M4 17 H20"
        className="stroke-ink"
        strokeWidth={1.4}
        fill="none"
        strokeLinecap="round"
      />
      {/* Vertical block seams on the lower course — three short ticks. */}
      <path
        d="M9 17 V14.4 M12 17 V13.8 M15 17 V14.4"
        className="stroke-ink"
        strokeWidth={1.2}
        fill="none"
        strokeLinecap="round"
      />
      {/* Arched entrance tunnel — filled sun so the home reads as "lit". */}
      <path
        d="M9.4 17 V13.6 A2.6 2.6 0 0 1 14.6 13.6 V17 Z"
        className="fill-sun stroke-ink"
        strokeWidth={2}
        strokeLinejoin="round"
      />
    </svg>
  );
}
