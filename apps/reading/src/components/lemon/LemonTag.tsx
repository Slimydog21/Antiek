import type { ReactNode } from "react";

/**
 * LemonTag — pill chip used in claim chips, status indicators, filter bars,
 * project-tree node decorations.
 *
 * A tag is static, so it is FLAT (design spec §4): a fill inside a 1px edge,
 * no shadow. The old raised z1 shadow made 56 read-only labels look like
 * buttons you could press. Filled colours carry their own boundary; the
 * default and muted tags draw the rule edge.
 */
type Colour = "default" | "sun" | "aurora" | "success" | "danger" | "muted";

type Props = {
  colour?: Colour;
  dot?: boolean;
  onRemove?: () => void;
  className?: string;
  children: ReactNode;
};

const colourMap: Record<Colour, string> = {
  default: "bg-card text-1 border-rule",
  sun:     "bg-sun text-ink border-transparent",
  aurora:  "bg-aurora text-ink border-transparent",
  // success (Q3/D2) — the done/met/passed green; aurora stays reserved for
  // AI-thinking. Filled like sun/aurora/danger. AA pairs (pinned in
  // tokens.contrast.test.ts): ice-0 white on the day green 5.90:1; day-ink
  // #0F1419 on the night sage ~10:1.
  success: "bg-success text-ice-0 dark:text-ink border-transparent",
  // text-ice-0 (#FFFFFF) → 4.69:1 contrast against bg-emperor — above
  // WCAG AA 4.5 floor. text-ice-1 was 4.12 (a11y_audit flagged this
  // as a serious contrast violation in S11).
  danger:  "bg-emperor text-ice-0 font-bold border-transparent",
  // muted: the secondary text role on the inset ground, a hairline edge
  // (quiet on purpose; pinned in controls.contrast.test.ts, both themes).
  muted:   "bg-inset text-2 border-hairline",
};

export function LemonTag({
  colour = "default", dot = false, onRemove, className = "", children,
}: Props) {
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full " +
        "font-mono text-xs font-semibold border " +
        `${colourMap[colour]} ${className}`
      }
    >
      {dot && (
        <span
          aria-hidden="true"
          className="w-1.5 h-1.5 rounded-full bg-ink dark:bg-bright shrink-0"
        />
      )}
      {children}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove"
          className="ml-0.5 leading-none text-current opacity-80 hover:opacity-100"
        >
          ×
        </button>
      )}
    </span>
  );
}

export default LemonTag;
