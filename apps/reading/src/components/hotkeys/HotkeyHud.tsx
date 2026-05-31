import { useEffect, useMemo, useState } from "react";

import LemonModal from "../lemon/LemonModal";
import { SHORTCUT_EVENTS } from "../../workspace/shortcuts";
import { readCustomHotkeys } from "../../workspace/persistence";
import { KeyChip } from "./KeyChip";
import {
  type BindingRow,
  BUILTIN_BINDINGS,
  PRODUCT_BINDINGS,
  SUBACTION_BINDINGS,
} from "./bindings";

import "./HotkeyHud.css";

export interface HotkeyHudProps {
  /**
   * Controlled-open override (used by Storybook / tests). When omitted the
   * HUD manages its own open state via the "?" key (SHORTCUT_EVENTS.HELP_TOGGLE).
   */
  open?: boolean;
  /** Called on close (controlled mode). */
  onClose?: () => void;
}

/**
 * HotkeyHud — the "?"-toggled keyboard cheat-sheet (milestones 3 + 6).
 *
 * Lists EVERY active binding grouped by section (Global, Panels, Products,
 * Sub-actions, Go-to chords, and the user's Custom per-entity bindings),
 * rendered with KeyChips. Built on LemonModal so it inherits the focus-trap,
 * ESC-to-close, scroll-lock, and restore-focus behaviour — and is screen-
 * reader navigable (role=dialog + the list is a real <dl>/<ul> structure).
 *
 * Toggling: listens for the HELP_TOGGLE window event that `shortcuts.ts`
 * fires on "?" (guarded so it never fires while typing). Drop ONE instance
 * high in the tree; on-bar placement is not required for discoverability.
 */
export function HotkeyHud({ open: controlledOpen, onClose }: HotkeyHudProps) {
  const isControlled = controlledOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const open = isControlled ? controlledOpen : internalOpen;

  // Re-read the custom bindings each time the HUD opens (cheap, and avoids
  // a global subscription) so newly-assigned custom hotkeys appear.
  const [customRows, setCustomRows] = useState<BindingRow[]>([]);

  useEffect(() => {
    if (isControlled) return;
    function onToggle() {
      setInternalOpen((v) => !v);
    }
    window.addEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, onToggle);
    return () => window.removeEventListener(SHORTCUT_EVENTS.HELP_TOGGLE, onToggle);
  }, [isControlled]);

  useEffect(() => {
    if (!open) return;
    const custom = readCustomHotkeys().bindings.map<BindingRow>((b) => ({
      id: b.id,
      spec: b.spec,
      label: b.label,
      group: "Your custom hotkeys",
      kind: "custom",
      route: b.route,
    }));
    setCustomRows(custom);
  }, [open]);

  const groups = useMemo(() => groupRows([
    ...BUILTIN_BINDINGS,
    ...PRODUCT_BINDINGS,
    ...SUBACTION_BINDINGS,
    ...customRows,
  ]), [customRows]);

  const handleClose = () => {
    if (isControlled) onClose?.();
    else setInternalOpen(false);
  };

  if (!open) return null;

  return (
    <LemonModal open onClose={handleClose} title="Keyboard shortcuts" size="lg">
      <p className="antiek-hud__intro">
        Press <kbd className="antiek-keychip__key">?</kbd> any time to open this. Built-in
        and product hotkeys are fixed; you can assign your own to a specific
        research, book, or writing project.
      </p>
      <div className="antiek-hud">
        {groups.map(([group, rows]) => (
          <section className="antiek-hud__group" key={group} aria-label={group}>
            <h3 className="antiek-hud__heading">{group}</h3>
            <ul className="antiek-hud__list">
              {rows.map((row) => (
                <li className="antiek-hud__row" key={row.id}>
                  <span className="antiek-hud__label">{row.label}</span>
                  <KeyChip binding={row.spec} label={row.label} />
                </li>
              ))}
            </ul>
          </section>
        ))}
        {customRows.length === 0 && (
          <p className="antiek-hud__empty">
            You haven&apos;t assigned any custom hotkeys yet. Use the
            &ldquo;Assign hotkey&rdquo; button on a research, book, or writing
            project to bind one.
          </p>
        )}
      </div>
    </LemonModal>
  );
}

/** Group binding rows by their `group`, preserving a stable section order. */
function groupRows(rows: BindingRow[]): Array<[string, BindingRow[]]> {
  const order = [
    "Global",
    "Products",
    "Sub-actions",
    "Panels",
    "Go to (chords)",
    "Your custom hotkeys",
  ];
  const map = new Map<string, BindingRow[]>();
  for (const r of rows) {
    const arr = map.get(r.group) ?? [];
    arr.push(r);
    map.set(r.group, arr);
  }
  const sorted: Array<[string, BindingRow[]]> = [];
  for (const g of order) {
    if (map.has(g)) {
      sorted.push([g, map.get(g)!]);
      map.delete(g);
    }
  }
  // any unforeseen groups, appended
  for (const [g, arr] of map) sorted.push([g, arr]);
  return sorted;
}
