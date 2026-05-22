import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

/**
 * LemonSelect — generic over the option value type V. Renders as a styled
 * button + a popover of options; keyboard ↑/↓/Enter/Esc.
 *
 * We don't use a native <select> so the visual language matches the rest
 * (sun-yellow border, chunky shadow, JetBrains-mono labels). The minor
 * a11y trade-off: a native select gets free OS-keyboard handling on
 * touch and mobile screen readers. We add the keyboard nav by hand and
 * mark the wrapper role="combobox".
 */
export type LemonOption<V> = {
  value: V;
  label: ReactNode;
  disabled?: boolean;
};

type Sizing = "sm" | "md" | "lg";

type Props<V> = {
  value: V | null;
  onChange: (v: V) => void;
  options: LemonOption<V>[];
  placeholder?: string;
  sizing?: Sizing;
  fullWidth?: boolean;
  className?: string;
  /** Accessible name for the combobox. Required for WCAG 2 AA
   *  (axe `aria-input-field-name`). Defaults to placeholder if absent. */
  "aria-label"?: string;
  /** Custom label renderer if you want the trigger label to differ from option label. */
  renderTriggerLabel?: (selected: LemonOption<V> | undefined) => ReactNode;
};

const heights: Record<Sizing, string> = {
  sm: "h-7  text-[12px]",
  md: "h-9  text-[13px]",
  lg: "h-11 text-[14px]",
};

export function LemonSelect<V>({
  value,
  onChange,
  options,
  placeholder = "Select…",
  sizing = "md",
  fullWidth = false,
  "aria-label": ariaLabel,
  className = "",
  renderTriggerLabel,
}: Props<V>) {
  const [open, setOpen] = useState(false);
  const [hoverIdx, setHoverIdx] = useState(() =>
    Math.max(0, options.findIndex((o) => o.value === value)),
  );
  const rootRef = useRef<HTMLDivElement>(null);

  const selected = useMemo(() => options.find((o) => o.value === value), [options, value]);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHoverIdx((i) => {
          for (let j = 1; j <= options.length; j++) {
            const n = (i + j) % options.length;
            if (!options[n].disabled) return n;
          }
          return i;
        });
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHoverIdx((i) => {
          for (let j = 1; j <= options.length; j++) {
            const n = (i - j + options.length) % options.length;
            if (!options[n].disabled) return n;
          }
          return i;
        });
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const o = options[hoverIdx];
        if (o && !o.disabled) {
          onChange(o.value);
          close();
        }
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, options, hoverIdx, onChange, close]);

  return (
    <div
      ref={rootRef}
      className={`relative inline-block ${fullWidth ? "w-full" : ""} ${className}`}
      role="combobox"
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-label={ariaLabel ?? placeholder}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={
          `inline-flex items-center justify-between gap-2 px-3 ${heights[sizing]} ` +
          "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright " +
          "border-edge border-sun rounded-hog " +
          "shadow-z1 dark:shadow-z1-night font-mono font-semibold " +
          "hover:-translate-x-[1px] hover:-translate-y-[1px] hover:shadow-z2 dark:hover:shadow-z2-night " +
          "transition-transform duration-75 " +
          (fullWidth ? "w-full" : "")
        }
      >
        <span className={`truncate ${selected ? "" : "text-ink-mute dark:text-moonlight"}`}>
          {renderTriggerLabel
            ? renderTriggerLabel(selected)
            : selected
              ? selected.label
              : placeholder}
        </span>
        <span className="shrink-0 text-ink-mute dark:text-moonlight">▾</span>
      </button>

      {open && (
        <ul
          role="listbox"
          className={
            "absolute top-[calc(100%+4px)] left-0 z-50 min-w-full " +
            "bg-ice-0 dark:bg-charcoal-2 " +
            "border-edge border-sun rounded-hog " +
            "shadow-z3 dark:shadow-z3-night " +
            "py-1 max-h-[280px] overflow-y-auto"
          }
        >
          {options.map((o, idx) => {
            const isSel = o.value === value;
            const isHover = idx === hoverIdx;
            return (
              <li
                key={String(o.value)}
                role="option"
                aria-selected={isSel}
                onMouseEnter={() => setHoverIdx(idx)}
                onClick={() => {
                  if (o.disabled) return;
                  onChange(o.value);
                  close();
                }}
                className={
                  "px-3 py-1.5 text-[13px] cursor-pointer " +
                  (o.disabled
                    ? "opacity-40 cursor-not-allowed "
                    : isHover
                      ? "bg-sun/25 dark:bg-sun/15 "
                      : "") +
                  (isSel ? "font-semibold text-ink dark:text-bright " : "text-ink dark:text-bright")
                }
              >
                {o.label}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default LemonSelect;
