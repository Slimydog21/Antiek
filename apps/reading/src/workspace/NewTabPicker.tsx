import { Suspense, lazy, useEffect, useState } from "react";

import { SHORTCUT_EVENTS } from "./shortcuts";

// The picker itself (the corpus lists, the filter and the spawn) loads on
// first open, so the entry chunk carries only this toggle.
const NewTabPickerContent = lazy(() => import("./NewTabPickerContent"));

export interface NewTabPickerProps {
  /**
   * Controlled-open override (used by Storybook / tests). When omitted the
   * picker manages its own open state via the keymap's NEWTAB_TOGGLE event
   * (prefix+c or ctrl+alt+c, and the document strip's + button).
   */
  open?: boolean;
  /** Called on close (controlled mode). */
  onClose?: () => void;
}

/**
 * NewTabPicker — the mount point for the new-tab picker (the D2 prefix+c
 * key). Drop ONE instance high in the tree (AppShell does).
 *
 * It listens for SHORTCUT_EVENTS.NEWTAB_TOGGLE, which the keymap dispatcher
 * fires for tab.new and toggleNewTabPicker() emits for the strip's +
 * button, and lazy-loads the content on first open. The dialog owns its
 * keys while open (its root carries data-keymap-owner="tab.new", so the
 * same key closes it), and closing returns focus to where it was.
 */
export function NewTabPicker({ open: controlledOpen, onClose }: NewTabPickerProps) {
  const isControlled = controlledOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const open = isControlled ? controlledOpen : internalOpen;

  useEffect(() => {
    if (isControlled) return;
    function onToggle() {
      setInternalOpen((v) => !v);
    }
    window.addEventListener(SHORTCUT_EVENTS.NEWTAB_TOGGLE, onToggle);
    return () => window.removeEventListener(SHORTCUT_EVENTS.NEWTAB_TOGGLE, onToggle);
  }, [isControlled]);

  if (!open) return null;

  const handleClose = () => {
    if (isControlled) onClose?.();
    else setInternalOpen(false);
  };

  return (
    <Suspense fallback={null}>
      <NewTabPickerContent onClose={handleClose} />
    </Suspense>
  );
}
