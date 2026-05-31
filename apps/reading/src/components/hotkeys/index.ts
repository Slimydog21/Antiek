/**
 * Hotkeys public surface — SPR-08.
 *
 * This barrel is the documented INTEGRATION SEAM for downstream sprints:
 *   - SPR-10 (penguin) imports the activation contract:
 *       PRODUCT_ACTIVATE_EVENT, ProductActivateDetail, emitProductActivate.
 *     A click handler and the hotkey handler both call `emitProductActivate`,
 *     so the penguin reacts identically to click and hotkey.
 *   - SPR-11 (on-bar chip placement) imports `<KeyChip>` + the binding
 *     tables (PRODUCT_BINDINGS / BUILTIN_BINDINGS / bindingForProduct) to
 *     drop chips into NavRail's (future) keyChipSlot and the launcher's
 *     sub-action chip slot — WITHOUT this sprint editing those shipped
 *     components.
 *   - Any entity surface imports `<AssignHotkey>` + `useCustomHotkeys`.
 *   - The shell mounts ONE `<HotkeyHud>` (the "?" cheat-sheet).
 */

export { KeyChip } from "./KeyChip";
export type { KeyChipProps } from "./KeyChip";

export { HotkeyHud } from "./HotkeyHud";
export type { HotkeyHudProps } from "./HotkeyHud";

export { AssignHotkey } from "./AssignHotkey";
export type { AssignHotkeyProps } from "./AssignHotkey";

export { useCustomHotkeys } from "./useCustomHotkeys";
export type {
  UseCustomHotkeys,
  CustomHotkeyInput,
  AssignResult,
} from "./useCustomHotkeys";

export {
  // activation contract (SPR-10)
  PRODUCT_ACTIVATE_EVENT,
  emitProductActivate,
  makeProductActivateEvent,
  // binding tables (SPR-11 chip placement)
  BUILTIN_BINDINGS,
  PRODUCT_BINDINGS,
  SUBACTION_BINDINGS,
  fixedBindings,
  bindingForProduct,
  // helpers
  normalizeBinding,
  formatBinding,
  ariaBinding,
  isChord,
  detectConflict,
  isBlockingConflict,
  reservedReason,
  RESERVED_COMBOS,
} from "./bindings";
export type {
  ProductActivateDetail,
  ActivationSource,
  BindingRow,
  BindingSpec,
  Conflict,
  ConflictKind,
} from "./bindings";
