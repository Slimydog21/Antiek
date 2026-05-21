import { forwardRef, useCallback, useImperativeHandle, useLayoutEffect, useRef } from "react";
import type { TextareaHTMLAttributes } from "react";

/**
 * LemonTextarea — multi-line input, auto-grows with maxRows clamp.
 * Used by ChatInputArea + notebook prose blocks. Cmd+Enter submits.
 *
 * The auto-grow trick: on every value change, reset rows to "1" then
 * read scrollHeight and grow rows until either scrollHeight stops
 * shrinking or we hit maxRows. Cheap, no measurement library.
 */
export type LemonTextareaProps = Omit<
  TextareaHTMLAttributes<HTMLTextAreaElement>,
  "onSubmit"
> & {
  minRows?: number;
  maxRows?: number;
  /** Called on Cmd/Ctrl + Enter when value is non-empty. */
  onSubmit?: (value: string) => void;
};

function lineHeightPx(el: HTMLTextAreaElement): number {
  const cs = window.getComputedStyle(el);
  const v = parseFloat(cs.lineHeight);
  return Number.isFinite(v) ? v : 20;
}

export const LemonTextarea = forwardRef<HTMLTextAreaElement, LemonTextareaProps>(
  (
    {
      minRows = 2,
      maxRows = 10,
      onSubmit,
      className = "",
      onKeyDown,
      onChange,
      value,
      defaultValue,
      ...rest
    },
    ref,
  ) => {
    const innerRef = useRef<HTMLTextAreaElement | null>(null);
    useImperativeHandle(ref, () => innerRef.current as HTMLTextAreaElement, []);

    const resize = useCallback(() => {
      const el = innerRef.current;
      if (!el) return;
      const lh = lineHeightPx(el);
      el.style.height = "auto";
      const desired = Math.min(el.scrollHeight, maxRows * lh + 16);
      el.style.height = `${Math.max(desired, minRows * lh + 16)}px`;
    }, [maxRows, minRows]);

    useLayoutEffect(() => {
      resize();
    }, [value, defaultValue, resize]);

    return (
      <textarea
        ref={innerRef}
        rows={minRows}
        value={value}
        defaultValue={defaultValue}
        onChange={(e) => {
          onChange?.(e);
          resize();
        }}
        onKeyDown={(e) => {
          onKeyDown?.(e);
          if (!e.defaultPrevented && (e.metaKey || e.ctrlKey) && e.key === "Enter") {
            const v = innerRef.current?.value ?? "";
            if (v.trim().length > 0) {
              onSubmit?.(v);
            }
          }
        }}
        className={
          "block w-full px-3 py-2 resize-none rounded-hog " +
          "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright " +
          "border-edge border-sun shadow-none focus:shadow-z1 " +
          "dark:focus:shadow-z1-night transition-shadow " +
          "font-sans text-[14px] leading-snug outline-none " +
          "placeholder:text-ink-mute dark:placeholder:text-moonlight " +
          className
        }
        {...rest}
      />
    );
  },
);
LemonTextarea.displayName = "LemonTextarea";

export default LemonTextarea;
