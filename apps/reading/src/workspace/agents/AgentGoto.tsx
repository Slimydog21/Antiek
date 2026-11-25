import { Suspense, lazy, useEffect, useState } from "react";

import { SHORTCUT_EVENTS } from "../shortcuts";

// The picker (the tree walk, the store, the modal) loads on first open, so
// the entry chunk carries only this toggle (NewTabPicker.tsx pattern).
const AgentGotoContent = lazy(() => import("./AgentGotoContent"));

export interface AgentGotoProps {
  /** Controlled-open override (stories / tests). */
  open?: boolean;
  onClose?: () => void;
}

/**
 * AgentGoto — the mount point for the agent goto picker (SPR-10 M5, herdr
 * B6; prefix+shift+g / ctrl+alt+g). Drop ONE instance high in the tree
 * (AppShell does). It listens for SHORTCUT_EVENTS.AGENT_GOTO_TOGGLE and
 * lazy-loads the content on first open. The dialog owns its keys while open
 * (its root carries data-keymap-owner="agents.goto", so the chord twin
 * closes it; the prefix never arms inside a modal).
 */
export function AgentGoto({ open: controlledOpen, onClose }: AgentGotoProps) {
  const isControlled = controlledOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const open = isControlled ? controlledOpen : internalOpen;

  useEffect(() => {
    if (isControlled) return;
    function onToggle() {
      setInternalOpen((v) => !v);
    }
    window.addEventListener(SHORTCUT_EVENTS.AGENT_GOTO_TOGGLE, onToggle);
    return () => window.removeEventListener(SHORTCUT_EVENTS.AGENT_GOTO_TOGGLE, onToggle);
  }, [isControlled]);

  if (!open) return null;

  const handleClose = () => {
    if (isControlled) onClose?.();
    else setInternalOpen(false);
  };

  return (
    <Suspense fallback={null}>
      <AgentGotoContent onClose={handleClose} />
    </Suspense>
  );
}

export default AgentGoto;
