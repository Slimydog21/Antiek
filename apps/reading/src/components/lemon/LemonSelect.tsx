import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";

/**
 * LemonSelect — generic over the option value type V. Renders as a styled
 * button + a popover of options; keyboard ↑/↓/Enter/Esc.
 *
 * We don't use a native <select> so the visual language matches the rest.
 * The minor a11y trade-off: a native select gets free OS-keyboard handling on
 * touch and mobile screen readers. We add the keyboard nav by hand and
 * mark the wrapper role="combobox".
 *
 * A select is a FIELD, so it is flat and bounded like LemonInput (card face,
 * 1px rule edge), not a raised key (design spec §4). The open list is a
 * floating island: the hard offset shadow and the popover rung of the z
 * ladder, so it sits over a modal it opens inside. ArrowDown/ArrowUp on the
 * closed trigger opens the list; Esc or a choice closes it and puts focus back
 * on the trigger instead of dropping it to <body>.
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
  sm: "h-7  text-xs",
  md: "h-9  text-sm",
  lg: "h-11 text-sm",
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
  const triggerRef = useRef<HTMLButtonElement>(null);

  const selected = useMemo(() => options.find((o) => o.value === value), [options, value]);

  const close = useCallback(() => setOpen(false), []);
  // Keyboard closes (Esc, Enter on an option, a click on an option) hand
  // focus back to the trigger; an outside click leaves it where it landed.
  const closeToTrigger = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  const onTriggerKeyDown = (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      setOpen(true);
    }
  };

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // Ours to handle: a modal around this select stays open.
        e.stopPropagation();
        closeToTrigger();
      }
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
          closeToTrigger();
        }
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, options, hoverIdx, onChange, close, closeToTrigger]);

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
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onTriggerKeyDown}
        className={
          `inline-flex items-center justify-between gap-2 px-3 ${heights[sizing]} ` +
          "bg-card text-1 border border-rule rounded-hog font-sans font-medium" +
          (fullWidth ? " w-full" : "")
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
            "absolute top-[calc(100%+4px)] left-0 z-popover min-w-full " +
            "bg-card border border-rule rounded-hog shadow-island " +
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
                aria-disabled={o.disabled || undefined}
                onMouseEnter={() => setHoverIdx(idx)}
                onClick={() => {
                  if (o.disabled) return;
                  onChange(o.value);
                  closeToTrigger();
                }}
                className={
                  "px-3 py-1.5 text-sm cursor-pointer " +
                  (o.disabled
                    ? "text-3 cursor-not-allowed "
                    : isHover
                      ? "bg-inset "
                      : "") +
                  (o.disabled ? "" : isSel ? "font-semibold text-1 " : "text-1")
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
