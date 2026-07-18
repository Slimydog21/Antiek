import { useCallback, useEffect, useRef, useState } from "react";

import LemonButton from "../lemon/LemonButton";
import { emitWernerExperience } from "../../werner/reactionBus";
import LemonModal from "../lemon/LemonModal";
import type { PersistedCustomHotkey } from "../../workspace/persistence";
import { KeyChip } from "./KeyChip";
import { useCustomHotkeys } from "./useCustomHotkeys";
import {
  isBlockingConflict,
  normalizeBinding,
  formatBinding,
  requiresModifierReason,
  SAFE_ASSIGNABLE,
} from "./bindings";

import "./AssignHotkey.css";

export interface AssignHotkeyProps {
  /** The entity to bind a hotkey to. */
  entityId: string;
  /** The fully-resolved route a press should navigate to. */
  route: string;
  /** Entity kind (drives the persisted label + HUD grouping). */
  entityKind: PersistedCustomHotkey["entityKind"];
  /** Operator-readable label for the entity (e.g. the investigation title). */
  label: string;
  /** Optional className for the trigger button. */
  className?: string;
}

/**
 * AssignHotkey — the per-entity "assign a hotkey" affordance (milestone 4/5).
 *
 * Drop this beside an investigation / book / deliverable / speak project. It
 * shows the current binding (if any) as a KeyChip, and opens a small capture
 * dialog (LemonModal — focus-trapped, ESC-closes) where the operator presses
 * the key they want. Conflicts are surfaced live:
 *   - blocking (built-in / reserved)  → the Save button is disabled.
 *   - overridable (another custom)    → a warning + a "Reassign anyway" path.
 *
 * NOTE on bindings.ts re-exports: the capture dialog needs `isBlockingConflict`,
 * `normalizeBinding`, and `formatBinding` from bindings.ts (imported above).
 */
export function AssignHotkey({
  entityId,
  route,
  entityKind,
  label,
  className,
}: AssignHotkeyProps) {
  const hk = useCustomHotkeys();
  const current = hk.bindingForEntity(entityId);
  const [open, setOpen] = useState(false);

  return (
    <span className={`antiek-assign-hotkey ${className ?? ""}`}>
      {current ? (
        <span className="antiek-assign-hotkey__current">
          <KeyChip binding={current.spec} label={`Hotkey for ${label}`} />
          <button
            type="button"
            className="antiek-assign-hotkey__clear"
            aria-label={`Remove hotkey for ${label}`}
            onClick={() => { emitWernerExperience("highlight"); hk.removeForEntity(entityId); }}
          >
            Remove
          </button>
        </span>
      ) : null}
      <LemonButton
        size="sm"
        variant="secondary"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        {current ? "Change hotkey" : "Assign hotkey"}
      </LemonButton>
      {open && (
        <CaptureDialog
          label={label}
          onClose={() => setOpen(false)}
          onSave={(spec, force) => {
            const res = hk.assign(
              { spec, route, entityId, entityKind, label },
              force,
            );
            if (res.ok) setOpen(false);
            return res;
          }}
          existingSelfId={current?.id}
          checkConflict={(spec) => hk.checkConflict(spec, current?.id)}
        />
      )}
    </span>
  );
}

interface CaptureDialogProps {
  label: string;
  onClose: () => void;
  onSave: (spec: string, force: boolean) => ReturnType<ReturnType<typeof useCustomHotkeys>["assign"]>;
  existingSelfId?: string;
  checkConflict: (spec: string) => ReturnType<ReturnType<typeof useCustomHotkeys>["checkConflict"]>;
}

function CaptureDialog({ label, onClose, onSave, checkConflict }: CaptureDialogProps) {
  const [captured, setCaptured] = useState<string | null>(null);
  const captureRef = useRef<HTMLDivElement>(null);

  // Capture ONE combo: a modifier (⌘/⌥/⇧) + a single key. We never capture a
  // sequence/chord — SPR-08 removed chords entirely, and `requiresModifierReason`
  // rejects both a bare key and a chord — so a custom binding is always a single
  // modifier-combo, matching the uniform ⌘+key scheme the products use.
  const onCaptureKey = useCallback((e: React.KeyboardEvent) => {
    // Let Tab/Escape behave normally for the focus trap + close (they must
    // keep bubbling to LemonModal's handlers).
    if (e.key === "Tab" || e.key === "Escape") return;
    e.preventDefault();
    // SPR-08 sharpen — this box is role="textbox" on a <div>, so the global
    // keydown handler's isTextEditing guard does NOT treat it as a text field;
    // without this, capturing "?" or "g" would fire the global HUD/chord
    // handlers (the HUD would pop over the capture modal and "?"/"g" could
    // never be bound). Stop the event reaching the window-level listener so
    // every key is capturable here.
    e.stopPropagation();
    const parts: string[] = [];
    if (e.metaKey || e.ctrlKey) parts.push("mod");
    if (e.altKey) parts.push("alt");
    if (e.shiftKey) parts.push("shift");
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase();
    // Ignore lone modifier presses.
    if (["shift", "meta", "control", "alt"].includes(key)) return;
    parts.push(key);
    setCaptured(normalizeBinding(parts.join("+")));
  }, []);

  useEffect(() => {
    const t = setTimeout(() => captureRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, []);

  const conflict = captured ? checkConflict(captured) : null;
  // SPR-08 sharpen — a bare single key is a footgun (it would hijack that key
  // app-wide whenever a non-text control is focused). Require a modifier/chord.
  const modifierReason = captured ? requiresModifierReason(captured) : null;
  // ⌘+key ONLY (defence-in-depth, mirrors useCustomHotkeys.assign's
  // SAFE_ASSIGNABLE gate): an ⌥-only (Option) combo carries a modifier, so it
  // clears requiresModifierReason, but the SPR-08 scheme is a single ⌘+<key>
  // with no Option namespace. Reject it here with a readable message so the
  // dialog never offers Save for an off-spec capture. The message is only
  // shown for a captured combo that has a modifier but isn't in the safe ⌘
  // range (so the bare-key case keeps its own clearer modifierReason text).
  const rangeReason =
    captured && !modifierReason && !SAFE_ASSIGNABLE.isWithinRange(captured)
      ? "Use ⌘ + a key (Option-only combos aren't assignable) — for example ⌘J."
      : null;
  const shapeReason = modifierReason ?? rangeReason;
  const blocking = isBlockingConflict(conflict) || shapeReason != null;
  const overridable = conflict != null && !isBlockingConflict(conflict);

  return (
    <LemonModal
      open
      onClose={onClose}
      title={`Assign a hotkey to ${label}`}
      size="sm"
      footer={
        <div className="antiek-assign-hotkey__footer">
          <LemonButton variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </LemonButton>
          {captured && (
            <LemonButton
              variant="primary"
              size="sm"
              disabled={!captured || blocking}
              onClick={() => { emitWernerExperience("note_saved"); onSave(captured, overridable); }}
            >
              {overridable ? "Reassign anyway" : "Save hotkey"}
            </LemonButton>
          )}
        </div>
      }
    >
      <p className="antiek-assign-hotkey__hint">
        Press the key (or key combo) you want. Built-in and product hotkeys
        can&apos;t be overridden.
      </p>
      <div
        ref={captureRef}
        className="antiek-assign-hotkey__capture"
        tabIndex={0}
        role="textbox"
        aria-label="Press the hotkey you want to assign"
        data-hotkey-capture
        onKeyDown={onCaptureKey}
      >
        {captured ? (
          <KeyChip binding={captured} label="Captured hotkey" size="md" />
        ) : (
          <span className="antiek-assign-hotkey__prompt">Press a key…</span>
        )}
      </div>
      {conflict && (
        <p
          className={
            "antiek-assign-hotkey__conflict" +
            (isBlockingConflict(conflict) ? " antiek-assign-hotkey__conflict--blocked" : "")
          }
          role="alert"
        >
          {conflict.message}
        </p>
      )}
      {!conflict && shapeReason && (
        <p
          className="antiek-assign-hotkey__conflict antiek-assign-hotkey__conflict--blocked"
          role="alert"
        >
          {shapeReason}
        </p>
      )}
      {captured && !conflict && !shapeReason && (
        <p className="antiek-assign-hotkey__ok" role="status">
          {formatBinding(captured)} is available.
        </p>
      )}
    </LemonModal>
  );
}
