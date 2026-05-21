import { forwardRef } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";

/**
 * LemonInput — single-line text input. Slots for left icon, right icon,
 * and an optional `kbdHint` chip (used by the command palette to show ⌘K).
 *
 * Focus state: sun-yellow border thickens, ink offset shadow appears.
 */
type Sizing = "sm" | "md" | "lg";

export type LemonInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "size"> & {
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
  kbdHint?: string;
  sizing?: Sizing;
  wrapperClassName?: string;
};

const heights: Record<Sizing, string> = {
  sm: "h-7",
  md: "h-9",
  lg: "h-11",
};

export const LemonInput = forwardRef<HTMLInputElement, LemonInputProps>(
  ({ iconLeft, iconRight, kbdHint, sizing = "md", wrapperClassName = "", className = "", ...rest }, ref) => (
    <label
      className={
        "inline-flex items-center gap-2 px-3 bg-ice-0 dark:bg-charcoal-2 " +
        "border-edge border-sun rounded-hog " +
        "transition-shadow shadow-none focus-within:shadow-z1 dark:focus-within:shadow-z1-night " +
        `${heights[sizing]} ${wrapperClassName}`
      }
    >
      {iconLeft && <span className="shrink-0 text-ink-soft dark:text-moonlight">{iconLeft}</span>}
      <input
        ref={ref}
        className={
          "flex-1 bg-transparent outline-none font-sans text-[13px] " +
          "text-ink dark:text-bright placeholder:text-ink-mute dark:placeholder:text-moonlight " +
          className
        }
        {...rest}
      />
      {iconRight && <span className="shrink-0 text-ink-soft dark:text-moonlight">{iconRight}</span>}
      {kbdHint && (
        <kbd
          className={
            "border-2 border-ink dark:border-bright rounded px-1.5 text-[10.5px] font-mono " +
            "bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright " +
            "shadow-[2px_2px_0_0_#0F1419] dark:shadow-[2px_2px_0_0_#8A7300]"
          }
        >
          {kbdHint}
        </kbd>
      )}
    </label>
  ),
);
LemonInput.displayName = "LemonInput";

export default LemonInput;
