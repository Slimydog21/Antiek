import { forwardRef, useId } from "react";
import type { ButtonHTMLAttributes, MouseEvent, ReactNode } from "react";

import { TipText, tipProps } from "../Tooltip";
import "./lemon.css";

/**
 * LemonButton — the core action primitive.
 *
 *   variant: primary (sun key), secondary (paper key), tertiary (flat), danger (red key)
 *   size:    sm | md | lg
 *
 * Physics (lemon.css): primary, secondary and danger are keycaps, a face over
 * a 3px frame. Hover lifts the face 0.5px and grows the frame 0.5px; press
 * sinks it; the frame's far edge never moves. Tertiary is flat and answers
 * hover with the --wash tint instead.
 *
 * The sun is spent on the primary key only (design spec §4). Secondary is a
 * paper face on a rule frame; danger is the danger fill on the ink edge.
 *
 * Disabled: pass `disabledReason` — a short sentence saying why the button
 * can't be used yet ("Type a question first"). The button then carries
 * aria-disabled instead of the native attribute, so it stays in the tab order
 * and under the pointer, shows the reason as a tip on hover and on keyboard
 * focus, and exposes it as its accessible description. Clicks and Enter/Space
 * do nothing while it is disabled (a submit button does not submit).
 * `disabled` still works for callers that have no reason to give, but a
 * button should never be quietly disabled: prefer the reason.
 */
type Variant = "primary" | "secondary" | "tertiary" | "danger";
type Size = "sm" | "md" | "lg";

export type LemonButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  iconRight?: ReactNode;
  fullWidth?: boolean;
  /** Why the button can't be used right now. Any non-empty string disables it. */
  disabledReason?: string | null | false;
};

export const base =
  "inline-flex items-center justify-center gap-2 font-sans font-medium " +
  "border rounded-hog " +
  // Disabled is a designed pair, not a fade: an inset face, the quiet text
  // tone and a hairline edge, flat (lemon.css drops the frame). Opacity would
  // also have dimmed the reason tip drawn on this element's ::after.
  "aria-disabled:cursor-not-allowed aria-disabled:bg-inset aria-disabled:text-3 " +
  "aria-disabled:border-hairline";

/** Exported for controls.contrast.test.ts, which resolves each pair through
 *  tokens.css in both themes. */
export const variants: Record<Variant, string> = {
  primary:
    "lemon-keycap bg-sun text-ink border-keycap-edge " +
    "hover:bg-sun-hover active:bg-sun-press",
  secondary: "lemon-keycap lemon-keycap--secondary bg-card text-1 border-rule",
  // Flat: nothing to lift, so hover answers with the wash tint.
  tertiary:
    "bg-transparent text-1 border-transparent " +
    "transition-colors duration-base ease-standard hover:bg-wash active:bg-wash",
  // bg-emperor is the danger FILL (white on it 6.09:1 in both themes).
  danger: "lemon-keycap bg-emperor text-ice-0 font-semibold border-keycap-edge",
};

const sizes: Record<Size, string> = {
  sm: "h-7  px-2.5 text-xs",
  md: "h-9  px-3.5 text-sm",
  lg: "h-11 px-5   text-sm",
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
      disabled,
      disabledReason,
      onClick,
      "aria-describedby": describedBy,
      ...rest
    },
    ref,
  ) => {
    const tipId = useId();
    const reason = disabledReason || null;
    const isDisabled = Boolean(disabled || reason);
    const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
      if (isDisabled) {
        e.preventDefault();
        return;
      }
      onClick?.(e);
    };
    return (
      <>
        <button
          {...rest}
          ref={ref}
          type={type}
          aria-disabled={isDisabled || undefined}
          {...tipProps(reason, tipId, describedBy)}
          onClick={handleClick}
          className={
            `${base} ${variants[variant]} ${sizes[size]} ` +
            `${fullWidth ? "w-full" : ""} ${className}`
          }
        >
          {icon && <span className="shrink-0">{icon}</span>}
          {children}
          {iconRight && <span className="shrink-0">{iconRight}</span>}
        </button>
        <TipText id={tipId} tip={reason} />
      </>
    );
  },
);
LemonButton.displayName = "LemonButton";

export default LemonButton;
