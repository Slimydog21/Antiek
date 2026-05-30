import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import { formatBinding, ariaBinding, isChord, normalizeBinding } from "./bindings";

import "./KeyChip.css";

export interface KeyChipProps {
  /**
   * The binding spec to render, e.g. "mod+k", "g r", "?". The chip is a
   * PURE render of this prop — when the owner rebinds an action it passes a
   * new spec and the chip updates. (Discoverability: chips are always shown,
   * including under reduced-motion.)
   */
  binding: string;
  /**
   * Accessible label for what the chip activates, e.g. "Command palette".
   * REQUIRED — a chip is never decorative-only: it is announced as
   * "<label>, keyboard shortcut <keys>" and carries `aria-keyshortcuts`.
   */
  label: string;
  /** Size variant; defaults to "sm" to sit inside a button. */
  size?: "sm" | "md";
  /** Optional extra className. */
  className?: string;
  /**
   * When true the chip is purely informational and is hidden from the a11y
   * tree IF an adjacent control already announces the same shortcut (e.g. a
   * button that itself has aria-keyshortcuts). Default false — the chip is
   * the announcer.
   */
  decorative?: boolean;
}

/**
 * KeyChip — a single inline, always-visible hotkey indicator.
 *
 * Visual idiom matches `LemonInput`'s `.lemon-kbd` (mono, light card,
 * 2px bottom border). A chord ("g r") renders as two glyph chips joined by
 * a faint "then"; a combo ("⌘K") renders as one chip. No animation — the
 * chip is static by design, so `usePrefersReducedMotion` only ever removes
 * the (already-subtle) hover transition.
 */
export function KeyChip({
  binding,
  label,
  size = "sm",
  className,
  decorative = false,
}: KeyChipProps) {
  const reduceMotion = usePrefersReducedMotion();
  const spec = normalizeBinding(binding);
  const display = formatBinding(spec);
  const aria = ariaBinding(spec);

  const a11yProps = decorative
    ? ({ "aria-hidden": true } as const)
    : ({
        role: "img" as const,
        "aria-label": `${label}, keyboard shortcut ${aria}`,
        "aria-keyshortcuts": aria,
      } as const);

  const classes = [
    "antiek-keychip",
    `antiek-keychip--${size}`,
    reduceMotion ? "antiek-keychip--no-motion" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  if (isChord(spec)) {
    const parts = display.split(" then ");
    return (
      <span className={classes} {...a11yProps}>
        {parts.map((p, i) => (
          <span key={i} className="antiek-keychip__seq">
            {i > 0 && (
              <span className="antiek-keychip__then" aria-hidden="true">
                then
              </span>
            )}
            <kbd className="antiek-keychip__key">{p}</kbd>
          </span>
        ))}
      </span>
    );
  }

  return (
    <span className={classes} {...a11yProps}>
      <kbd className="antiek-keychip__key">{display}</kbd>
    </span>
  );
}
