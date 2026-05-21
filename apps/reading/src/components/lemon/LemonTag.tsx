import type { ReactNode } from "react";

/**
 * LemonTag — pill chip used in claim chips, status indicators, filter bars,
 * project-tree node decorations. Brand: sun-yellow outline, ink offset shadow
 * (day) / sun-deep shadow (night).
 */
type Colour = "default" | "sun" | "aurora" | "danger" | "muted";

type Props = {
  colour?: Colour;
  dot?: boolean;
  onRemove?: () => void;
  className?: string;
  children: ReactNode;
};

const colourMap: Record<Colour, string> = {
  default: "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright",
  sun:     "bg-sun text-ink",
  aurora:  "bg-aurora text-ink",
  danger:  "bg-emperor text-ice-1 border-ink dark:border-ink",
  muted:   "bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight border-rule dark:border-charcoal-2 shadow-none",
};

export function LemonTag({
  colour = "default", dot = false, onRemove, className = "", children,
}: Props) {
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full " +
        "font-mono text-[11.5px] font-semibold " +
        "border-edge border-sun shadow-z1 dark:shadow-z1-night " +
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
          className="ml-0.5 leading-none text-ink/60 hover:text-ink dark:text-bright/60 dark:hover:text-bright"
        >
          ×
        </button>
      )}
    </span>
  );
}

export default LemonTag;
