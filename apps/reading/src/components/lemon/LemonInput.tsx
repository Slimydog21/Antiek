import { forwardRef } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";

/**
 * LemonInput — single-line text input. Slots for left icon, right icon,
 * and an optional `kbdHint` chip (used by the command palette to show ⌘K).
 *
 * Fields are flat and bounded (design spec §4): the card surface inside a
 * 1px rule edge (3.55:1 on the page in both themes; the old sun edge was
 * 1.29:1 by day). Focus draws the one focus ring (--focus: ink by day, sun at
 * night) around the whole field, on the label, because the input inside is
 * borderless.
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
        "inline-flex items-center gap-2 px-3 bg-card " +
        "border border-rule rounded-hog " +
        "focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-focus " +
        `${heights[sizing]} ${wrapperClassName}`
      }
    >
      {iconLeft && <span className="shrink-0 text-ink-soft dark:text-moonlight">{iconLeft}</span>}
      <input
        ref={ref}
        className={
          "flex-1 bg-transparent outline-none font-sans text-sm " +
          "text-ink dark:text-bright placeholder:text-ink-mute dark:placeholder:text-moonlight " +
          className
        }
        {...rest}
      />
      {iconRight && <span className="shrink-0 text-ink-soft dark:text-moonlight">{iconRight}</span>}
      {kbdHint && (
        <kbd
          className={
            "border border-rule rounded px-1.5 text-xxs font-mono " +
            "bg-inset text-2"
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
