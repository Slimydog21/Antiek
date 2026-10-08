import { Suspense, lazy, useEffect, useState } from "react";

import { SHORTCUT_EVENTS } from "./shortcuts";

// The picker itself (the registry read and the project rows) loads on
// first open, so the entry chunk carries only this toggle.
const ProjectPickerContent = lazy(() => import("./ProjectPickerContent"));

export interface ProjectPickerProps {
  /**
   * Controlled-open override (used by Storybook / tests). When omitted the
   * picker manages its own open state via the keymap's PROJECT_SELECT_TOGGLE
   * event (prefix+shift+p or ctrl+alt+p, and the sidebar's project row).
   */
  open?: boolean;
  /** Called on close (controlled mode). */
  onClose?: () => void;
}

/**
 * ProjectPicker — the mount point for the account-project picker (the D2
 * project level). Drop ONE instance high in the tree (AppShell does).
 *
 * It listens for SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, which the keymap
 * dispatcher fires for project.select and toggleProjectPicker() emits for
 * the sidebar's project row, and lazy-loads the content on first open. The
 * dialog owns its keys while open (its root carries
 * data-keymap-owner="project.select", so the same key closes it), and
 * closing returns focus to where it was.
 */
export function ProjectPicker({ open: controlledOpen, onClose }: ProjectPickerProps) {
  const isControlled = controlledOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  // SPR-04 gear 1: the geared switch asks for a row to land on
  // (toggleProjectPicker({ focusId })); a plain toggle carries none.
  const [focusId, setFocusId] = useState<string | undefined>(undefined);
  const open = isControlled ? controlledOpen : internalOpen;

  useEffect(() => {
    if (isControlled) return;
    function onToggle(e: Event) {
      const detail = (e as CustomEvent<{ focusId?: string } | undefined>).detail;
      setFocusId(typeof detail?.focusId === "string" ? detail.focusId : undefined);
      setInternalOpen((v) => !v);
    }
    window.addEventListener(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, onToggle);
    return () => window.removeEventListener(SHORTCUT_EVENTS.PROJECT_SELECT_TOGGLE, onToggle);
  }, [isControlled]);

  if (!open) return null;

  const handleClose = () => {
    if (isControlled) onClose?.();
    else setInternalOpen(false);
  };

  return (
    <Suspense fallback={null}>
      <ProjectPickerContent onClose={handleClose} initialFocusId={focusId} />
    </Suspense>
  );
}
