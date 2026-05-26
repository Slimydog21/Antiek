import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { press } from "../../design/motion";

/**
 * LemonButton — the core action primitive.
 *
 *   variant: primary (sun fill), secondary (card fill), tertiary (ghost), danger (emperor fill)
 *   size:    sm | md | lg
 *
 * Brand: sun-yellow border on every fill-variant. Day shadow casts in ink,
 * night shadow casts in sun-deep (auto-handled by the dark: classes).
 *
 * Motion (U-05): the hover-lift + press come from the shared `press`
 * primitive in design/motion.ts so the lift and tap feel identical to
 * every other Lemon surface and run on the motion token (duration-base),
 * not a per-component magic number. Fill variants get the lift; tertiary
 * is a ghost with no shadow, so it gets a bg shift on hover instead.
 * Disabled drops shadow + reduces opacity.
 */
type Variant = "primary" | "secondary" | "tertiary" | "danger";
type Size = "sm" | "md" | "lg";

export type LemonButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  iconRight?: ReactNode;
  fullWidth?: boolean;
};

const base =
  "inline-flex items-center justify-center gap-2 font-mono font-semibold " +
  "border-edge rounded-hog " +
  "disabled:opacity-50 disabled:pointer-events-none";

const variants: Record<Variant, string> = {
  primary: `bg-sun text-ink border-sun shadow-z1 dark:shadow-z1-night ${press}`,
  secondary:
    "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright border-sun " +
    `shadow-z1 dark:shadow-z1-night ${press}`,
  // Ghost: no shadow to lift, so the press primitive doesn't apply —
  // a bg shift on hover is its tactile signal instead.
  tertiary:
    "bg-transparent text-ink dark:text-bright border-transparent shadow-none " +
    "transition-colors duration-base ease-standard " +
    "hover:bg-ice-3 dark:hover:bg-charcoal-1",
  // Danger: bg-emperor on text-ice-0 gives 4.69:1 contrast (above
  // WCAG AA 4.5 floor). The previous text-ice-1 was 4.12 — axe
  // flagged it as a serious contrast violation in the S11 a11y audit.
  danger: `bg-emperor text-ice-0 font-bold border-ink shadow-z1 dark:shadow-z1-night ${press}`,
};

const sizes: Record<Size, string> = {
  sm: "h-7  px-2.5 text-[12px]",
  md: "h-9  px-3.5 text-[13px]",
  lg: "h-11 px-5   text-[14px]",
};

export const LemonButton = forwardRef<HTMLButtonElement, LemonButtonProps>(
  (
    {
      variant = "secondary",
      size = "md",
      icon,
      iconRight,
      fullWidth,
      className = "",
      children,
      type = "button",
      ...rest
    },
    ref,
  ) => (
    <button
      ref={ref}
      type={type}
      className={
        `${base} ${variants[variant]} ${sizes[size]} ` +
        `${fullWidth ? "w-full" : ""} ${className}`
      }
      {...rest}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      {children}
      {iconRight && <span className="shrink-0">{iconRight}</span>}
    </button>
  ),
);
LemonButton.displayName = "LemonButton";

export default LemonButton;
