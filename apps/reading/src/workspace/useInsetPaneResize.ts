import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent, RefObject } from "react";

const MIN_PRIMARY_WIDTH = 320;
const MIN_RIGHT_WIDTH = 280;
const KEY_STEP = 16;

/** The preference survives temporary space constraints; only the rendered
 * width is clamped. Geometry belongs to this layout instance, not a tab. */
export function useInsetPaneResize({
  containerRef,
  enabled,
  defaultWidth,
  reservedWidth,
  primaryDockWidth,
}: {
  containerRef: RefObject<HTMLDivElement>;
  enabled: boolean;
  defaultWidth: number;
  reservedWidth: number;
  primaryDockWidth: number;
}) {
  const [preferredWidth, setPreferredWidth] = useState<number | null>(null);
  const [containerWidth, setContainerWidth] = useState<number | null>(null);
  const drag = useRef<{ pointerId: number; x: number; width: number } | null>(null);

  useLayoutEffect(() => {
    if (!enabled) return;
    const container = containerRef.current;
    if (!container) return;
    const measure = () => {
      const measured = container.getBoundingClientRect().width;
      if (measured > 0) setContainerWidth(measured);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(container);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, [containerRef, enabled]);

  useEffect(() => { if (!enabled) drag.current = null; }, [enabled]);

  const available = containerWidth === null ? null : Math.max(0, containerWidth - reservedWidth);
  // An embedded cockpit can be narrower than the viewport tier. Preserve
  // both panes there rather than overflowing their actual container.
  const primaryMinimum = MIN_PRIMARY_WIDTH + primaryDockWidth;
  const minimum = available === null ? MIN_RIGHT_WIDTH : Math.min(MIN_RIGHT_WIDTH, available * MIN_RIGHT_WIDTH / (MIN_RIGHT_WIDTH + primaryMinimum));
  const maximum = available === null ? Math.max(defaultWidth, preferredWidth ?? defaultWidth)
    : Math.max(minimum, available - Math.min(primaryMinimum, available - minimum));
  const clamp = (value: number) => Math.round(Math.min(maximum, Math.max(minimum, value)));
  const width = clamp(preferredWidth ?? defaultWidth);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!enabled || event.button !== 0 || drag.current) return;
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointerId: event.pointerId, x: event.clientX, width };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = drag.current;
    if (!enabled || !start || start.pointerId !== event.pointerId) return;
    setPreferredWidth(clamp(start.width + start.x - event.clientX));
  };
  const onPointerEnd = useCallback((event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!enabled || event.altKey || event.ctrlKey || event.metaKey) return;
    const step = event.shiftKey ? KEY_STEP * 3 : KEY_STEP;
    switch (event.key) {
      case "ArrowLeft": setPreferredWidth(clamp(width + step)); break;
      case "ArrowRight": setPreferredWidth(clamp(width - step)); break;
      case "Home": setPreferredWidth(clamp(minimum)); break;
      case "End": setPreferredWidth(clamp(maximum)); break;
      case "Enter": setPreferredWidth(null); break;
      default: return;
    }
    event.preventDefault();
    event.stopPropagation();
  };

  return { width, minimum: Math.round(minimum), maximum: Math.round(maximum),
    onPointerDown, onPointerMove, onPointerUp: onPointerEnd, onPointerCancel: onPointerEnd,
    onLostPointerCapture: onPointerEnd, onKeyDown };
}
