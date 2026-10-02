import { zIndex } from "../../design/zIndex";
import { formatBinding } from "./bindings";
import { readPrefix } from "./keymap";
import { usePrefixArmed } from "./prefixState";

import "./PrefixChip.css";

/**
 * The quiet "prefix armed" chip. After the operator presses the prefix
 * (ctrl+b by default) the next key goes to the keymap; this chip is the only
 * sign of that mode, and it stays until that key or Esc (there is no timeout).
 *
 * The status region is always mounted so a screen reader hears the change;
 * the visible chip renders only while armed.
 */
export function PrefixChip() {
  const armed = usePrefixArmed();
  return (
    // The toast rung: a transient status line, like a toast. It never arms
    // while a modal is open, so it never has to sit over one.
    <div
      role="status"
      aria-live="polite"
      className="antiek-prefix-chip__region"
      style={{ zIndex: zIndex.toast }}
    >
      {armed && (
        <span className="antiek-prefix-chip" data-testid="prefix-armed-chip">
          <kbd className="antiek-prefix-chip__key" aria-hidden="true">
            {formatBinding(readPrefix())}
          </kbd>
          <span className="antiek-prefix-chip__text">Prefix armed: press a key, or Esc</span>
        </span>
      )}
    </div>
  );
}
