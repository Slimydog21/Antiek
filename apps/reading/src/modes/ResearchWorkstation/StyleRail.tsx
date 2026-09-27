import { useRef, useState, type CSSProperties, type KeyboardEvent, type WheelEvent } from "react";

import type { ProjectionStyle } from "../../api/styles";

export interface StyleRailProps {
  styles: ProjectionStyle[];
  selected: string;
  onSelect: (name: string) => void;
  /**
   * Session-local fallback lineage (name → parent name) for a style the server
   * sent no `parent` for. Persisted provenance on the style wins.
   */
  provenance?: Record<string, string>;
  ariaLabel?: string;
}

/**
 * The scroll of styles: one horizontal `listbox` with arrow / Home / End
 * parity and vertical-wheel → horizontal scroll translation while the rail is
 * active. Shared by the artifact wheel (`StyleWheel`) and the document preview
 * (`DocumentStylePreview`) so the product has exactly one rail, not two that
 * drift.
 */
export default function StyleRail({
  styles,
  selected,
  onSelect,
  provenance = {},
  ariaLabel = "Artifact styles",
}: StyleRailProps) {
  const [railActive, setRailActive] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const chooseAt = (index: number) => {
    const style = styles[(index + styles.length) % styles.length];
    if (!style) return;
    onSelect(style.name);
    requestAnimationFrame(() => document.getElementById(`style-${style.name}`)?.focus());
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") chooseAt(0);
    else if (event.key === "End") chooseAt(styles.length - 1);
    else chooseAt(index + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1));
  };

  const onWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (!railActive || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
    event.preventDefault();
    event.currentTarget.scrollLeft += event.deltaY;
  };

  return (
    <div
      className="style-wheel__rail"
      ref={listRef}
      role="listbox"
      aria-label={ariaLabel}
      aria-orientation="horizontal"
      onWheel={onWheel}
      onMouseEnter={() => setRailActive(true)}
      onMouseLeave={() => setRailActive(false)}
      onFocusCapture={() => setRailActive(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setRailActive(false);
      }}
    >
      {styles.map((style, index) => {
        const derivedFrom = style.parent ?? provenance[style.name];
        const derivedLabel = derivedFrom
          ? styles.find((s) => s.name === derivedFrom)?.label ?? derivedFrom
          : null;
        return (
          <button
            id={`style-${style.name}`}
            key={style.name}
            type="button"
            role="option"
            aria-selected={style.name === selected}
            tabIndex={style.name === selected ? 0 : -1}
            className="style-wheel__option"
            onClick={() => onSelect(style.name)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            <span
              className="style-wheel__swatch"
              style={
                {
                  "--style-theme": "var(--sun-deep)",
                } as CSSProperties
              }
              aria-hidden="true"
            />
            <strong>{style.label}</strong>
            <span className="style-wheel__option-meta">
              {style.builtin ? "Built in" : "Your fork"}
              {style.source_fidelity ? " · source-first" : ""}
              {derivedLabel ? ` · from ${derivedLabel}` : ""}
            </span>
          </button>
        );
      })}
    </div>
  );
}
