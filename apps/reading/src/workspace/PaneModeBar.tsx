/**
 * PaneModeBar — the one-row mode bar (SPR-01 M4, R9). A bold pill per
 * active non-default mode plus live key hints; nothing renders in the
 * default mode. RESIZE gets the distinct tint (herdr's RESIZE-on-mauve
 * rule, in our palette: sun-deep on a sun wash, against the prefix chip's
 * neutral card — the PREFIX pill itself is PrefixChip's, reused, not
 * re-drawn). Token classes only; no animation, so reduced-motion is
 * trivially safe. The bar never takes pointer events (the prefix chip's
 * rule: it cannot cover a control the operator reaches for).
 */
import { zIndex } from "../design/zIndex";
import { usePaneResizeMode } from "./paneResizeMode";

export function PaneModeBar() {
  const active = usePaneResizeMode((s) => s.active);
  const columns = usePaneResizeMode((s) => s.columns);
  if (!active) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Resize mode"
      data-pane-mode-bar
      className="pointer-events-none fixed bottom-[108px] left-1/2 flex -translate-x-1/2 items-center gap-1.5"
      style={{ zIndex: zIndex.toast }}
    >
      <span className="inline-flex items-center rounded-full border border-sun-deep bg-sun-deep/15 px-2 py-0.5 font-mono text-xxs font-semibold uppercase tracking-wider text-sun-deep">
        Resize
      </span>
      <span className="inline-flex items-center rounded-full border border-hairline bg-ice-0 px-2 py-0.5 text-xxs text-ink-soft shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-moonlight dark:shadow-z1-night">
        {columns
          ? "Columns are measured, not split — nothing to nudge here. Enter or Esc leaves."
          : "h/l width · j/k height · Enter commits · Esc restores"}
      </span>
    </div>
  );
}

export default PaneModeBar;
