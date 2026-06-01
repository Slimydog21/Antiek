/**
 * Hotkeys public surface — SPR-08.
 *
 * This barrel is the documented INTEGRATION SEAM for downstream sprints:
 *   - SPR-06 (penguin) imports the activation contract:
 *       PRODUCT_ACTIVATE_EVENT, ProductActivateDetail, emitProductActivate.
 *     A click handler and the hotkey handler both call `emitProductActivate`,
 *     so the penguin reacts identically to click and hotkey.
 *   - SPR-07 (on-bar chip placement) imports `<KeyChip>` + `chipBindings()`
 *     (+ bindingForProduct) to drop a ⌘+key chip next to each NavRail door
 *     and the launcher's sub-action rows — WITHOUT this sprint editing those
 *     shipped components. Every spec it receives is a single ⌘+key combo
 *     (isChord false), so the chips render one glyph group, no "then".
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
  // activation contract (the penguin / SPR-06 click≡hotkey parity)
  PRODUCT_ACTIVATE_EVENT,
  emitProductActivate,
  makeProductActivateEvent,
  // binding tables (SPR-07 chip placement)
  BUILTIN_BINDINGS,
  PRODUCT_BINDINGS,
  SUBACTION_BINDINGS,
  fixedBindings,
  bindingForProduct,
  // ── THE MAP SPR-07 CONSUMES ──────────────────────────────────────────
  // chipBindings() returns one { id, spec, label, ariaLabel, productId,
  // actionId, route } per product + sub-action — every `spec` a single ⌘+key
  // combo. SPR-07 iterates it and drops a <KeyChip binding={spec} …/> next to
  // each NavRail door (the EXPOSE half of the SPR-07↔SPR-08 dependency).
  // bindingForProduct(productId, actionId?) resolves one entry directly.
  chipBindings,
  // helpers
  normalizeBinding,
  formatBinding,
  ariaBinding,
  isChord,
  detectConflict,
  isBlockingConflict,
  reservedReason,
  requiresModifierReason,
  RESERVED_COMBOS,
  SAFE_ASSIGNABLE,
} from "./bindings";
export type {
  ProductActivateDetail,
  ActivationSource,
  BindingRow,
  BindingSpec,
  ChipBinding,
  Conflict,
  ConflictKind,
} from "./bindings";
