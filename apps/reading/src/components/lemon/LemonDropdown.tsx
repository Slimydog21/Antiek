import { cloneElement, useCallback, useEffect, useId, useRef, useState } from "react";
import type {
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  ReactElement,
  ReactNode,
} from "react";

import { TipText, tipProps } from "../Tooltip";

/**
 * LemonDropdown — renderless trigger + popover.
 *
 *   <LemonDropdown trigger={<LemonButton>Open</LemonButton>}>
 *     {({ close }) => (
 *       <>
 *         <LemonMenuItem onClick={close}>Item 1</LemonMenuItem>
 *         <LemonMenuItem onClick={close}>Item 2</LemonMenuItem>
 *       </>
 *     )}
 *   </LemonDropdown>
 *
 * Closes on outside-click + Esc. No external floating-ui dep; we position
 * absolute below the trigger and align left.
 *
 * Keyboard contract (WAI-ARIA menu button): the trigger carries
 * aria-haspopup="menu" and aria-expanded. Enter, Space or ArrowDown opens the
 * menu on its first item, ArrowUp on its last. Inside, ArrowDown/ArrowUp move
 * with wrap-around, Home/End jump. A disabled item (aria-disabled) is still
 * focusable, so its reason can be read, but cannot be activated; an item
 * disabled with the native attribute cannot take focus and is skipped, so it
 * can never trap the arrow keys. Esc, or choosing an item, closes the menu
 * and puts focus back on the trigger; an outside click or Tab away closes it
 * and leaves focus where it went.
 *
 * The menu is a floating island: 1px rule edge, the hard offset shadow, and
 * the popover rung of the z ladder so it opens over a modal.
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

const ITEM = '[role="menuitem"]:not(:disabled)';

export function LemonDropdown({
  trigger,
  children,
  align = "below-left",
  menuClassName = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  // Which item to focus once the menu has rendered (keyboard opens only).
  const pendingFocus = useRef<"first" | "last" | null>(null);

  const triggerEl = () =>
    rootRef.current?.querySelector<HTMLElement>(":scope > [data-dropdown-trigger] > *") ?? null;
  const items = () => Array.from(menuRef.current?.querySelectorAll<HTMLElement>(ITEM) ?? []);

  /** Close and return focus to the trigger (Esc, an item chosen). */
  const close = useCallback(() => {
    setOpen(false);
    triggerEl()?.focus();
  }, []);

  const openWith = (focus: "first" | "last" | null) => {
    pendingFocus.current = focus;
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    if (pendingFocus.current) {
      const list = items();
      (pendingFocus.current === "first" ? list[0] : list[list.length - 1])?.focus();
      pendingFocus.current = null;
    }
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // Ours to handle: a modal around this menu stays open.
        e.stopPropagation();
        close();
      }
    };
    const onFocusOut = (e: FocusEvent) => {
      const next = e.relatedTarget as Node | null;
      if (next && !rootRef.current?.contains(next)) setOpen(false);
    };
    const root = rootRef.current;
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    root?.addEventListener("focusout", onFocusOut);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      root?.removeEventListener("focusout", onFocusOut);
    };
  }, [open, close]);

  // A disabled trigger (aria-disabled, still focusable for its reason)
  // must not open the menu.
  const triggerDisabled = () => triggerEl()?.getAttribute("aria-disabled") === "true";

  const handleTriggerClick = () => {
    if (open) setOpen(false);
    else if (!triggerDisabled()) openWith(null);
  };

  const handleTriggerKeyDown = (e: ReactKeyboardEvent) => {
    if (!open && triggerDisabled()) return;
    if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
      e.preventDefault();
      if (open && e.key !== "ArrowDown") setOpen(false);
      else if (open) items()[0]?.focus();
      else openWith("first");
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (open) items().at(-1)?.focus();
      else openWith("last");
    }
  };

  const handleMenuKeyDown = (e: ReactKeyboardEvent) => {
    const list = items();
    if (list.length === 0) return;
    const idx = list.indexOf(document.activeElement as HTMLElement);
    let next: number | null = null;
    if (e.key === "ArrowDown") next = (idx + 1) % list.length;
    else if (e.key === "ArrowUp") next = (idx - 1 + list.length) % list.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = list.length - 1;
    if (next === null) return;
    e.preventDefault();
    list[next]?.focus();
  };

  const triggerWithAria = cloneElement(trigger, {
    "aria-haspopup": "menu",
    "aria-expanded": open,
    "aria-controls": open ? menuId : undefined,
  });

  return (
    <div ref={rootRef} className="relative inline-block">
      {/* The wrapper owns the click + key handling so any trigger works,
          including ones that do not forward handlers; the ARIA state is
          cloned onto the trigger itself, where assistive tech reads it. */}
      <span
        data-dropdown-trigger=""
        className="inline-flex"
        onClick={handleTriggerClick}
        onKeyDown={handleTriggerKeyDown}
      >
        {triggerWithAria}
      </span>
      {open && (
        <div
          ref={menuRef}
          id={menuId}
          onKeyDown={handleMenuKeyDown}
          className={
            "absolute top-[calc(100%+4px)] z-popover min-w-[180px] " +
            (align === "below-right" ? "right-0" : "left-0") +
            " bg-card border border-rule rounded-hog shadow-island " +
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
 * Dock left / Dock right / Float / Close items.
 *
 * `disabledReason` works as on LemonButton: the item stays focusable,
 * shows the reason as a tip and as its description, and does nothing when
 * activated. The highlight follows keyboard focus as well as the pointer. */
export function LemonMenuItem({
  onClick,
  disabled,
  disabledReason,
  icon,
  hint,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  disabledReason?: string | null | false;
  icon?: ReactNode;
  hint?: string;
  children: ReactNode;
}) {
  const tipId = useId();
  const reason = disabledReason || null;
  const isDisabled = Boolean(disabled || reason);
  return (
    <>
      <button
        type="button"
        onClick={(e: ReactMouseEvent) => {
          if (isDisabled) {
            e.preventDefault();
            return;
          }
          onClick();
        }}
        aria-disabled={isDisabled || undefined}
        {...tipProps(reason, tipId, undefined)}
        role="menuitem"
        className={
          "w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm text-1 " +
          "hover:bg-wash focus-visible:bg-wash focus-visible:outline-offset-[-2px] " +
          "aria-disabled:text-3 aria-disabled:cursor-not-allowed aria-disabled:hover:bg-transparent"
        }
      >
        {icon && <span className="shrink-0 w-4 text-center">{icon}</span>}
        <span className="flex-1">{children}</span>
        {hint && (
          <kbd className="shrink-0 border border-rule rounded px-1 text-xxs font-mono leading-tight bg-inset text-2">
            {hint}
          </kbd>
        )}
      </button>
      <TipText id={tipId} tip={reason} />
    </>
  );
}

export default LemonDropdown;
