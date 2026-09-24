import { Suspense, lazy, useEffect, useLayoutEffect, useRef, useState } from "react";

import { SHORTCUT_EVENTS } from "../../workspace/shortcuts";

// The sheet itself (the rendered keymap, its filter and styles) loads on
// first open, so the entry chunk carries only this toggle.
const KeySheet = lazy(() => import("./KeySheet"));

export interface HotkeyHudProps {
  /**
   * Controlled-open override (used by Storybook / tests). When omitted the
   * HUD manages its own open state via the keymap's HELP_TOGGLE event
   * (`?` or prefix+?).
   */
  open?: boolean;
  /** Called on close (controlled mode). */
  onClose?: () => void;
}

/**
 * HotkeyHud — the mount point for the key sheet (MS-01; was the SPR-08
 * cheat-sheet). Drop ONE instance high in the tree (AppShell does).
 *
 * It listens for SHORTCUT_EVENTS.HELP_TOGGLE, which the keymap dispatcher
 * fires for `?` and prefix+?, lazy-loads KeySheet (rendered from keymap.ts)
 * and, on close, returns focus to the element that had it when the sheet
 * opened.
 *
 * Summoned, never persistent: a reference that is always on screen occludes
 * the work. The NavRail keycaps carry the always-visible hints.
 */
export function HotkeyHud({ open: controlledOpen, onClose }: HotkeyHudProps) {
  const isControlled = controlledOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const open = isControlled ? controlledOpen : internalOpen;
  const openerRef = useRef<Element | null>(null);

  useEffect(() => {
    if (isControlled) return;
    function onToggle() {
      setInternalOpen((v) => !v);
    }
    window.addEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, onToggle);
    return () => window.removeEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, onToggle);
  }, [isControlled]);

  // Remember who had focus as the sheet opens (a layout effect runs before
  // the dialog's own effect moves focus into it), and give it back when the
  // sheet closes, whichever way it closed.
  useLayoutEffect(() => {
    if (open) {
      openerRef.current = document.activeElement;
      return;
    }
    const opener = openerRef.current;
    openerRef.current = null;
    if (opener instanceof HTMLElement && opener.isConnected && opener !== document.body) {
      opener.focus();
    }
  }, [open]);

  if (!open) return null;

  const handleClose = () => {
    if (isControlled) onClose?.();
    else setInternalOpen(false);
  };

  return (
    <Suspense fallback={null}>
      <KeySheet onClose={handleClose} />
    </Suspense>
  );
}
