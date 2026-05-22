import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

/**
 * LemonModal — centered modal with backdrop, ESC-to-close, outside-click-to-close,
 * hand-rolled focus trap. Renders via portal to document.body so it floats above
 * any workspace panel z-stack introduced in S3.
 *
 *   sizes:  sm  → max-w-md
 *           md  → max-w-2xl  (default)
 *           lg  → max-w-4xl
 *           full→ max-w-[96vw]
 *
 * Z-index: 100. Above panels (1-50), below toasts (200).
 *
 * The focus trap is intentionally tiny (~20 LoC). It captures Tab and Shift-Tab
 * on the modal root and cycles between the first and last focusable element.
 * Robust enough for our forms; not a full a11y library.
 */
type Size = "sm" | "md" | "lg" | "full";

const widths: Record<Size, string> = {
  sm: "max-w-md",
  md: "max-w-2xl",
  lg: "max-w-4xl",
  full: "max-w-[96vw]",
};

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), ' +
  'select:not([disabled]), [tabindex]:not([tabindex="-1"])';

type Props = {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  footer?: ReactNode;
  size?: Size;
  /** Disables the outside-click + Esc handlers. Used by confirm-modals. */
  forceUserAction?: boolean;
  children: ReactNode;
};

export function LemonModal({
  open,
  onClose,
  title,
  footer,
  size = "md",
  forceUserAction = false,
  children,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // ESC handler
  useEffect(() => {
    if (!open || forceUserAction) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose, forceUserAction]);

  // Focus trap: keep focus inside dialog while open
  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusables = () =>
      Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => !el.hasAttribute("aria-hidden") && el.offsetParent !== null,
      );

    // initial focus
    const initial = focusables()[0] ?? dialog;
    initial.focus();

    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener("keydown", handler);
    return () => dialog.removeEventListener("keydown", handler);
  }, [open]);

  if (!open) return null;

  const overlay = (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      onMouseDown={() => {
        if (!forceUserAction) onClose();
      }}
      aria-hidden={!open}
    >
      <div className="absolute inset-0 bg-ink/30 dark:bg-void/60 backdrop-blur-[1px]" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        // S11 a11y: dialog needs an accessible name. If a string title
        // is passed, use it; if the title is a ReactNode (chip + count),
        // fall back to a generic "Dialog" so axe-core's
        // `aria-dialog-name` passes. Operators can override by passing
        // a plain-string title.
        aria-label={typeof title === "string" ? title : "Dialog"}
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
        className={
          `relative w-full ${widths[size]} mx-4 ` +
          "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright " +
          "border-edge border-sun rounded-hog-lg shadow-lift dark:shadow-lift-night " +
          "outline-none"
        }
      >
        {title && (
          <header className="px-5 py-3 border-b-edge border-sun flex items-center justify-between">
            <h2 className="font-mono text-sm uppercase tracking-wider">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-ink-soft dark:text-moonlight hover:text-ink dark:hover:text-bright leading-none text-lg"
            >
              ✕
            </button>
          </header>
        )}
        <div className="px-5 py-4">{children}</div>
        {footer && (
          <footer className="px-5 py-3 border-t-edge border-sun">{footer}</footer>
        )}
      </div>
    </div>
  );

  // SSR guard (Vite + React 18 client-only — but harmless).
  if (typeof document === "undefined") return null;
  return createPortal(overlay, document.body);
}

export default LemonModal;
