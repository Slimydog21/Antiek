import { useEffect, useRef, useState } from "react";

import BlockRepository from "./BlockRepository";
import type { RepositoryHit } from "./writeApi";

interface WriteFieldKitProps {
  onSelect: (hit: RepositoryHit) => void;
  /** Deterministic review state; production leaves this false. */
  initialOpen?: boolean;
}

/** Tablet/mobile access to the existing evidence repository. */
export default function WriteFieldKit({ onSelect, initialOpen = false }: WriteFieldKitProps) {
  const [open, setOpen] = useState(initialOpen);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        requestAnimationFrame(() => triggerRef.current?.focus());
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const inside = dialogRef.current?.contains(document.activeElement);
      if (!inside) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const close = () => {
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };

  return (
    <div className="lg:hidden" data-testid="write-field-kit">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        tabIndex={open ? -1 : 0}
        onClick={() => setOpen(true)}
        className="fixed bottom-16 right-3 z-40 flex items-center gap-2 border-2 border-ink bg-sun px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-wider text-ink shadow-z2 focus:outline-none focus:ring-2 focus:ring-ocean focus:ring-offset-2 dark:border-bright dark:text-ink"
      >
        <span aria-hidden="true">▰</span>
        Evidence blocks
      </button>

      {open && (
        <>
          <div
            aria-hidden="true"
            onClick={close}
            data-testid="write-field-kit-backdrop"
            className="fixed inset-0 z-40 bg-ink/40"
          />
          <aside
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="write-field-kit-title"
            className="fixed inset-x-2 bottom-2 z-50 flex max-h-[68vh] min-h-[22rem] flex-col overflow-hidden border-2 border-ink bg-ice-0 shadow-z3 dark:border-bright dark:bg-charcoal-2"
          >
            <header className="flex items-center justify-between border-b-2 border-ink bg-sun px-4 py-2 text-ink dark:border-bright">
              <div>
                <p className="font-mono text-[9px] font-bold uppercase tracking-[0.22em]">
                  Field kit · provenance intact
                </p>
                <h2 id="write-field-kit-title" className="font-serif text-base font-semibold">
                  Choose evidence to place
                </h2>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={close}
                className="border border-ink px-2 py-1 font-mono text-[10px] font-bold uppercase focus:outline-none focus:ring-2 focus:ring-ocean"
              >
                Close
              </button>
            </header>
            <p className="border-b border-rule px-4 py-2 font-serif text-xs text-ink-soft dark:border-charcoal-1 dark:text-moonlight">
              Pick a source block, then choose its exact seam in the outline.
            </p>
            <div className="min-h-0 flex-1 p-4">
              <BlockRepository
                onAdd={(hit) => {
                  onSelect(hit);
                  close();
                }}
              />
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
