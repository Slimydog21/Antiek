import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";

/**
 * LemonDropdown — renderless trigger + popover.
 *
 *   <LemonDropdown trigger={<LemonButton>Open</LemonButton>}>
 *     {({ close }) => (
 *       <>
 *         <button onClick={close}>Item 1</button>
 *         <button onClick={close}>Item 2</button>
 *       </>
 *     )}
 *   </LemonDropdown>
 *
 * Closes on outside-click + Esc. No external floating-ui dep; we position
 * absolute below the trigger and align left. Sufficient for panel kebab
 * menus and mode-page kebabs; S11 hardens overflow if real screens need it.
 */
type ChildArg = { close: () => void };

type Props = {
  trigger: ReactElement;
  children: (arg: ChildArg) => ReactNode;
  /** "below-left" (default), "below-right" — anchors popover to trigger edge. */
  align?: "below-left" | "below-right";
  /** Width override; default auto. */
  menuClassName?: string;
};

export function LemonDropdown({
  trigger,
  children,
  align = "below-left",
  menuClassName = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((o) => !o), []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  // Keyboard contract (a11y): Enter/Space toggles; ArrowDown opens when
  // closed and moves focus to the first menu item when open (menu items are
  // real buttons, so Tab/Enter navigation then works natively). Mouse
  // behavior is unchanged.
  const handleTriggerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (open) {
        menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
      } else {
        toggle();
      }
    }
  };

  // Menu arrow-key navigation: ArrowDown/ArrowUp move focus between
  // menuitems with wrap-around; Enter/Space activate natively (real buttons).
  const handleMenuKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
    );
    if (items.length === 0) return;
    const idx = items.indexOf(document.activeElement as HTMLElement);
    const next =
      e.key === "ArrowDown"
        ? (idx + 1) % items.length
        : (idx - 1 + items.length) % items.length;
    items[next]?.focus();
  };

  return (
    <div ref={rootRef} className="relative inline-block">
      {/* Clone trigger with click + keyboard handlers bound to toggle */}
      <span onClick={toggle} onKeyDown={handleTriggerKeyDown}>{trigger}</span>
      {open && (
        <div
          ref={menuRef}
          onKeyDown={handleMenuKeyDown}
          className={
            "absolute top-[calc(100%+4px)] z-50 min-w-[180px] " +
            (align === "below-right" ? "right-0" : "left-0") +
            " bg-ice-0 dark:bg-charcoal-2 " +
            "border-edge border-sun rounded-hog " +
            "shadow-z3 dark:shadow-z3-night " +
            "py-1 " + menuClassName
          }
          role="menu"
        >
          {children({ close })}
        </div>
      )}
    </div>
  );
}

/** Convenience component for menu items — matches the visual language.
 *
 * S8 acceptance: every panel-system action should show its keyboard
 * shortcut. The optional `hint` prop renders a kbd chip on the right
 * (matching the LemonInput `kbdHint` styling), used by PanelHandle's
 * Dock left / Dock right / Float / Close items. */
export function LemonMenuItem({
  onClick,
  disabled,
  icon,
  hint,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  icon?: ReactNode;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      role="menuitem"
      className={
        "w-full flex items-center gap-2 px-3 py-1.5 text-left text-[13px] " +
        "text-ink dark:text-bright " +
        "hover:bg-sun/20 dark:hover:bg-sun/15 " +
        "disabled:opacity-50 disabled:pointer-events-none"
      }
    >
      {icon && <span className="shrink-0 w-4 text-center">{icon}</span>}
      <span className="flex-1">{children}</span>
      {hint && (
        <kbd className="shrink-0 border border-ink dark:border-bright rounded px-1 text-[10px] font-mono leading-tight bg-ice-1 dark:bg-charcoal-1 text-ink dark:text-bright">
          {hint}
        </kbd>
      )}
    </button>
  );
}

export default LemonDropdown;
