/**
 * BrainMark — the home control's mark (replaces IglooMark; brain edition).
 *
 * The operator's brand: the brain is the mascot AND the logo. The rail home
 * button therefore reads as the brain — two hemispheres with a central
 * sulcus, surface folds, and a sun spark at the centre: the brain is
 * "alight". Drawn inline in the same geometric idiom IglooMark used (crisp
 * pure vector at 24–28 px rail size, tokens only — no raw hex), so the
 * lint:tokens gate stays green.
 *
 * Purely presentational: aria-hidden, no role. The semantics (link/button
 * role, aria-label, focus ring) live on the control that wraps it
 * (NavRail's home button).
 */
type Props = { size?: number; className?: string };

export default function BrainMark({ size = 28, className }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {/* The two hemispheres — one continuous silhouette with a central
          cleft. Warm rounded lobes, not a clinical oval. */}
      <path
        d="M12 3.4 C 8.2 2.2, 3.9 4.7, 4.7 9.4 C 5.3 12.9, 7.1 15, 8.3 16.9 C 9.1 18.2, 10.4 19.1, 12 18.7 C 13.6 19.1, 14.9 18.2, 15.7 16.9 C 16.9 15, 18.7 12.9, 19.3 9.4 C 20.1 4.7, 15.8 2.2, 12 3.4 Z"
        className="fill-ice-0 stroke-ink"
        strokeWidth={2}
        strokeLinejoin="round"
      />
      {/* Central sulcus — the cleft between the hemispheres. */}
      <path
        d="M12 4.6 C 11.3 8.6, 12.7 13.4, 12 18"
        className="stroke-ink"
        strokeWidth={1.3}
        fill="none"
        strokeLinecap="round"
      />
      {/* Surface folds — short arcs echoing the hemisphere curves. */}
      <path
        d="M6.9 8.6 C 8.2 7.8, 9.6 7.8, 10.7 8.7"
        className="stroke-ink"
        strokeWidth={1.2}
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M6.4 12.8 C 7.9 12, 9.6 12.2, 10.8 13"
        className="stroke-ink"
        strokeWidth={1.2}
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M17.1 8.6 C 15.8 7.8, 14.4 7.8, 13.3 8.7"
        className="stroke-ink"
        strokeWidth={1.2}
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M17.6 12.8 C 16.1 12, 14.4 12.2, 13.2 13"
        className="stroke-ink"
        strokeWidth={1.2}
        fill="none"
        strokeLinecap="round"
      />
      {/* The spark — sun token at the centre: the brain is alight. */}
      <circle cx="12" cy="10.6" r="1.5" className="fill-sun" />
    </svg>
  );
}
