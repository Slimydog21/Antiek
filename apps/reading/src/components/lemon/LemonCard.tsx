import type { ReactNode } from "react";

/**
 * LemonCard — container primitive with optional title row + footer slot.
 *
 * Cards are FLAT and bounded (design spec §4): a surface inside a 1px rule
 * edge, no shadow. Depth is for things you can press (LemonButton's keycap)
 * and for things that float (popover, modal, palette). The old default cast
 * a 5px shadow, deeper than a resting button's 3px, so a static card read as
 * more pressable than the buttons on it.
 *
 *   elevation: flat (default) | z1 | z2 | z3
 *     `z1` is the lowest legacy tier and renders flat under that rule; `z2`
 *     and `z3` mean "this card floats" and get the one island offset.
 *   colour:    card | sun | aurora | ink | glacial
 */
type Elevation = "flat" | "z1" | "z2" | "z3";
type Colour = "card" | "sun" | "aurora" | "ink" | "glacial";

type Props = {
  title?: ReactNode;
  footer?: ReactNode;
  elevation?: Elevation;
  colour?: Colour;
  className?: string;
  children: ReactNode;
};

const elev: Record<Elevation, string> = {
  flat: "",
  z1: "",
  z2: "shadow-island",
  z3: "shadow-island",
};

const bg: Record<Colour, string> = {
  card:    "bg-card text-1",
  sun:     "bg-sun text-ink",
  aurora:  "bg-aurora text-ink",
  ink:     "bg-ink text-ice-1",
  glacial: "bg-inset text-1",
};

export function LemonCard({
  title,
  footer,
  elevation = "flat",
  colour = "card",
  className = "",
  children,
}: Props) {
  return (
    <section
      className={
        `border border-rule rounded-hog ${bg[colour]} ${elev[elevation]} ${className}`
      }
    >
      {title && (
        <header
          className={
            "px-4 py-2.5 border-b border-hairline font-mono text-xs uppercase tracking-wider"
          }
        >
          {title}
        </header>
      )}
      <div className="px-4 py-3">{children}</div>
      {footer && (
        <footer className="px-4 py-2.5 border-t border-hairline">{footer}</footer>
      )}
    </section>
  );
}

export default LemonCard;
