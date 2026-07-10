import type { ReactNode } from "react";

/**
 * LemonCard — container primitive with optional title row + footer slot.
 * Brand: sun-yellow border, chunky offset shadow. Day ink-shadow,
 * night sun-deep-shadow via dark: classes.
 *
 *   elevation: z1 | z2 | z3
 *   colour:    card | sun | aurora | ink | glacial
 */
type Elevation = "z1" | "z2" | "z3";
type Colour = "card" | "sun" | "aurora" | "ink" | "glacial" | "parchment";

type Props = {
  title?: ReactNode;
  footer?: ReactNode;
  elevation?: Elevation;
  colour?: Colour;
  className?: string;
  children: ReactNode;
};

const elev: Record<Elevation, string> = {
  z1: "shadow-z1 dark:shadow-z1-night",
  z2: "shadow-z2 dark:shadow-z2-night",
  z3: "shadow-z3 dark:shadow-z3-night",
};

const bg: Record<Colour, string> = {
  card:    "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright",
  sun:     "bg-sun text-ink",
  aurora:  "bg-aurora text-ink",
  ink:     "bg-ink text-ice-1",
  glacial: "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright",
  parchment: "bg-parchment dark:bg-charcoal-2 text-ink dark:text-bright",
};

export function LemonCard({
  title,
  footer,
  elevation = "z2",
  colour = "card",
  className = "",
  children,
}: Props) {
  return (
    <section
      className={
        `border-edge border-sun rounded-hog ${bg[colour]} ${elev[elevation]} ${className}`
      }
    >
      {title && (
        <header
          className={
            "px-4 py-2.5 border-b-edge border-sun font-mono text-xs uppercase tracking-wider"
          }
        >
          {title}
        </header>
      )}
      <div className="px-4 py-3">{children}</div>
      {footer && (
        <footer className="px-4 py-2.5 border-t-edge border-sun">{footer}</footer>
      )}
    </section>
  );
}

export default LemonCard;
