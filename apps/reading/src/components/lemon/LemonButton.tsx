import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * LemonButton — the core action primitive.
 *
 *   variant: primary (sun fill), secondary (card fill), tertiary (ghost), danger (emperor fill)
 *   size:    sm | md | lg
 *
 * Brand: sun-yellow border on every fill-variant. Day shadow casts in ink,
 * night shadow casts in sun-deep (auto-handled by the dark: classes).
 *
 * Hover lifts 2px and goes to z3 shadow. Active resets to flat. Disabled
 * drops shadow + reduces opacity.
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
  "border-edge rounded-hog transition-transform duration-75 " +
  "active:translate-x-[2px] active:translate-y-[2px] active:!shadow-none " +
  "disabled:opacity-50 disabled:pointer-events-none";

const variants: Record<Variant, string> = {
  primary:
    "bg-sun text-ink border-sun shadow-z1 dark:shadow-z1-night " +
    "hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-z3 dark:hover:shadow-z3-night",
  secondary:
    "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright border-sun " +
    "shadow-z1 dark:shadow-z1-night " +
    "hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-z3 dark:hover:shadow-z3-night",
  tertiary:
    "bg-transparent text-ink dark:text-bright border-transparent shadow-none " +
    "hover:bg-ice-3 dark:hover:bg-charcoal-1",
  danger:
    "bg-emperor text-ice-1 border-ink shadow-z1 dark:shadow-z1-night " +
    "hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-z3 dark:hover:shadow-z3-night",
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
