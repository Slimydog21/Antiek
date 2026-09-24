import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

import { enter } from "../../design/motion";
import { LemonButton } from "./LemonButton";

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
 * Z-index: the `modal` rung of the ladder (tokens.css --z-modal). Above
 * panels and windows, below popovers (a select inside a modal opens over it),
 * toasts and tips.
 *
 * Focus (WCAG 2.4.3): opening remembers the element that had focus and closing
 * gives focus back to it, so a keyboard user lands where they were instead of
 * at the top of the page. Initial focus goes to the first element marked
 * `data-autofocus`, else the first text field, else the first control in the
 * body or footer (for a confirm, the left-most action, usually Cancel), and
 * only then the close button. Tab and Shift-Tab cycle inside the dialog.
 *
 * The dialog is named by its title (aria-labelledby). It is a floating island:
 * a 1px rule edge and the hard offset shadow, and it never outgrows the
 * viewport — the body scrolls instead.
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

const FIELD =
  'input:not([disabled]):not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), ' +
  "textarea:not([disabled]), select:not([disabled])";

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

/** Rendered and exposed: not inside a hidden or aria-hidden subtree, and
 *  (where the browser can say) actually laid out. */
function visible(el: HTMLElement): boolean {
  if (el.closest('[hidden], [aria-hidden="true"]')) return false;
  return typeof el.checkVisibility === "function" ? el.checkVisibility() : true;
}

/** Where focus starts when the dialog opens. */
function initialFocusTarget(dialog: HTMLElement): HTMLElement {
  const marked = dialog.querySelector<HTMLElement>("[data-autofocus]");
  if (marked) return marked;
  const field = Array.from(dialog.querySelectorAll<HTMLElement>(FIELD)).find(visible);
  if (field) return field;
  const controls = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(visible);
  return controls.find((el) => !el.hasAttribute("data-modal-close")) ?? controls[0] ?? dialog;
}

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
  const titleId = useId();
  // The element that had focus when the modal opened. Read during the render
  // that flips `open` to true: by the time an effect runs, a child with
  // autoFocus may already have taken focus.
  const openerRef = useRef<Element | null>(null);
  const wasOpenRef = useRef(false);
  if (open && !wasOpenRef.current && typeof document !== "undefined") {
    openerRef.current = document.activeElement;
  }
  wasOpenRef.current = open;

  // Drives the motion.ts `enter` primitive: the dialog mounts at
  // data-enter=false (faded, 4px low) and flips to true on the next frame,
  // so the fade-rise runs exactly once per open. Under reduced-motion the
  // motion.css guard collapses the transition — the modal simply appears.
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    if (!open) {
      setEntered(false);
      return;
    }
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(raf);
  }, [open]);

  // ESC handler
  useEffect(() => {
    if (!open || forceUserAction) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose, forceUserAction]);

  // Initial focus, the Tab trap, and focus return on close.
  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const opener = openerRef.current;

    const focusables = () =>
      Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(visible);

    if (!dialog.contains(document.activeElement)) initialFocusTarget(dialog).focus();

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
    return () => {
      dialog.removeEventListener("keydown", handler);
      // Give focus back only if it is still ours to give: inside the dialog,
      // or dropped to <body> by the dialog unmounting. If the user clicked
      // into something else to dismiss it, leave focus there.
      const active = document.activeElement;
      const ours = !active || active === document.body || dialog.contains(active);
      if (ours && opener instanceof HTMLElement && opener.isConnected) {
        opener.focus({ preventScroll: true });
      }
    };
  }, [open]);

  if (!open) return null;

  const overlay = (
    <div
      className="fixed inset-0 z-modal flex items-center justify-center"
      onMouseDown={() => {
        if (!forceUserAction) onClose();
      }}
    >
      <div className="absolute inset-0 bg-ink/30 dark:bg-void/60 backdrop-blur-[1px]" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        // Named by the title element (string or node); a titleless modal
        // falls back to a generic name so axe `aria-dialog-name` passes.
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : "Dialog"}
        tabIndex={-1}
        data-enter={entered}
        onMouseDown={(e) => e.stopPropagation()}
        className={
          `relative w-full ${widths[size]} mx-4 max-h-[calc(100dvh-2rem)] flex flex-col ` +
          "bg-card text-1 border border-rule rounded-hog-lg shadow-island " +
          enter +
          " outline-none"
        }
      >
        {title && (
          <header className="shrink-0 pl-5 pr-3 py-2.5 border-b border-hairline flex items-center justify-between gap-3">
            <h2 id={titleId} className="font-serif text-lg font-semibold leading-snug">
              {title}
            </h2>
            <LemonButton
              variant="tertiary"
              size="sm"
              onClick={onClose}
              aria-label="Close"
              data-modal-close=""
              className="w-7 !px-0 shrink-0"
            >
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              </svg>
            </LemonButton>
          </header>
        )}
        <div className="px-5 py-4 min-h-0 overflow-y-auto">{children}</div>
        {footer && (
          <footer className="shrink-0 px-5 py-3 border-t border-hairline">{footer}</footer>
        )}
      </div>
    </div>
  );

  // SSR guard (Vite + React 18 client-only — but harmless).
  if (typeof document === "undefined") return null;
  return createPortal(overlay, document.body);
}

export default LemonModal;
