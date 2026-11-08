import { isFeatureOn } from "../../lib/featureFlags";
/**
 * keymap.ts — Every built-in global binding is a row in {@link KEYMAP}.
 * Widgets and editors own local keys; user-defined bindings use the dispatcher.
 *
 * One dispatcher (workspace/shortcuts.ts) reads this table and owns every
 * global key. The key sheet (KeySheet.tsx, `prefix+?`) renders it, and every
 * bound control's `aria-keyshortcuts` comes from `ariaKeyshortcutsFor`
 * (bindings.ts), so the handlers, the sheet and the accessibility tree read
 * one source.
 *
 * ─────────────────────────────────────────────────────────────────────
 * The model (operator ruling D2, 2026-09-24)
 * ─────────────────────────────────────────────────────────────────────
 * A herdr-style PREFIX plus browser-safe DIRECT CHORDS. The record is
 * docs/decisions/mothership-keys-herdr-prefix.md; it supersedes SPR-08's
 * no-leader rule. The SPR-08 ⌘ combos stay as rows of origin `legacy-SPR-08`.
 *
 *   - Prefix: default `ctrl+b` (herdr's), configurable ({@link setPrefix}).
 *     Press it, release, press the next key. It stays armed until that next
 *     key or Esc, with NO timeout, as in herdr and tmux; the "prefix armed"
 *     chip shows while it waits. It never arms from a text field or inside a
 *     modal, where ctrl+b already means something (on macOS it moves the
 *     caret back one character).
 *
 *   - Direct chords: the `ctrl+alt` family, matched on `KeyboardEvent.code`,
 *     the physical key. WHY ctrl+alt AND NOT alt: macOS composes plain alt
 *     (option) chords into characters, so alt+1 arrives with e.key "¡" and
 *     types "¡" into every text field. herdr's keyboard doc maps the defaults
 *     of ten terminals and the GNOME/KDE globals and finds ctrl+alt almost
 *     untouched everywhere. Matching on e.code also means a chord never
 *     depends on what the OS composed. An AltGr press (Windows/Linux layouts
 *     that type characters with ctrl+alt) reports the AltGraph modifier and
 *     is never taken as a chord.
 *
 * Row fields:
 *   action     what the key does (a key of ACTIONS; the dispatcher's handler
 *              map must have one handler per action, see validateKeymap).
 *   prefixKey  the key pressed after the prefix ("g", "?", "shift+x").
 *   chord      a direct key: a ctrl+alt chord, a legacy ⌘ combo ("mod" is
 *              ⌘ on a Mac and Ctrl elsewhere), or the lone "?".
 *   scope      "outside-text": never fires while typing in a text field or
 *              the Write editor. "anywhere": also fires there (⌘K, chords).
 *              Inside a modal only the modal's own toggle fires.
 *   origin     "herdr-default": herdr's default key for the same meaning,
 *              adopted by D2. "D2": decided by the operator in D2.
 *              "legacy-SPR-08": the ⌘ scheme SPR-08 shipped.
 *   decision   the record a herdr-default or D2 row answers to.
 *   platforms  omitted = everywhere.
 *   spr08      for legacy rows, the SPR-08 table bindings.ts republishes it
 *              in (its label is the action's label).
 */

/** The decision record every herdr-default and D2 row cites. */
export const KEYMAP_DECISION =
  "docs/decisions/mothership-keys-herdr-prefix.md (specs/antiek-mothership/DECISIONS.md D2)";

export type KeymapOrigin = "herdr-default" | "D2" | "legacy-SPR-08" | "lane-A-proposed" | "lane-Sweep-SPR-02" | "lane-Sweep-SPR-01";
export type KeymapScope = "anywhere" | "outside-text";
export type KeymapTask = "find" | "go" | "panels" | "help";
export type Platform = "mac" | "other";

export interface ActionMeta {
  /** What the key sheet (and the SPR-08 binding rows) call the action. Its
   *  key-sheet group and any caveat live with the sheet, in keymapView.ts. */
  label: string;
  /** Product doors: the activation the click and the key share. */
  productId?: string;
  actionId?: string;
  route?: string;
}

// Landing gate (SPR-01 M1, antiek.flag.pane.flow, default OFF), read ONCE at
// load: with the flag off the pane rows AND their labels are main's; with it
// on they are the packet's flow rows (S05 ctrl+alt+l → arrangement toggle,
// arrow focus, shift+arrow reorder) and wording.
const PANE_FLOW_ON = isFeatureOn("pane.flow");

export const ACTIONS = {
  "palette.toggle": { label: "Switcher (command palette)" },
  "keysheet.toggle": { label: "Key sheet (this list)" },
  "projecttree.toggle": { label: "Toggle the sidebar (project tree)" },
  "aisidecar.toggle": { label: "Toggle the AI sidecar" },
  "panel.focusPrev": { label: PANE_FLOW_ON ? "Focus the previous panel or product window" : "Focus the previous panel" },
  "panel.focusNext": { label: PANE_FLOW_ON ? "Focus the next panel or product window" : "Focus the next panel" },
  "panel.closeFloating": { label: "Close the focused floating panel" },
  "pane.focusLeft": { label: PANE_FLOW_ON ? "Pane: focus the previous pane" : "Pane: focus the left pane" },
  "pane.focusRight": { label: PANE_FLOW_ON ? "Pane: focus the next pane" : "Pane: focus the right pane" },
  "pane.reorderLeft": { label: "Pane: move the focused pane left" },
  "pane.reorderRight": { label: "Pane: move the focused pane right" },
  // SPR-01 M6 (R11): the ten numbered arrangements — one jump and one
  // move-and-follow action per slot, plus cycle/last-used. Digit 0 is slot
  // 10, Omarchy's own ordering.
  "pane.arrangement1": { label: "Panes: jump to arrangement 1" },
  "pane.arrangement2": { label: "Panes: jump to arrangement 2" },
  "pane.arrangement3": { label: "Panes: jump to arrangement 3" },
  "pane.arrangement4": { label: "Panes: jump to arrangement 4" },
  "pane.arrangement5": { label: "Panes: jump to arrangement 5" },
  "pane.arrangement6": { label: "Panes: jump to arrangement 6" },
  "pane.arrangement7": { label: "Panes: jump to arrangement 7" },
  "pane.arrangement8": { label: "Panes: jump to arrangement 8" },
  "pane.arrangement9": { label: "Panes: jump to arrangement 9" },
  "pane.arrangement10": { label: "Panes: jump to arrangement 10" },
  "pane.moveToArrangement1": { label: "Panes: move the focused pane into arrangement 1 and follow" },
  "pane.moveToArrangement2": { label: "Panes: move the focused pane into arrangement 2 and follow" },
  "pane.moveToArrangement3": { label: "Panes: move the focused pane into arrangement 3 and follow" },
  "pane.moveToArrangement4": { label: "Panes: move the focused pane into arrangement 4 and follow" },
  "pane.moveToArrangement5": { label: "Panes: move the focused pane into arrangement 5 and follow" },
  "pane.moveToArrangement6": { label: "Panes: move the focused pane into arrangement 6 and follow" },
  "pane.moveToArrangement7": { label: "Panes: move the focused pane into arrangement 7 and follow" },
  "pane.moveToArrangement8": { label: "Panes: move the focused pane into arrangement 8 and follow" },
  "pane.moveToArrangement9": { label: "Panes: move the focused pane into arrangement 9 and follow" },
  "pane.moveToArrangement10": { label: "Panes: move the focused pane into arrangement 10 and follow" },
  "pane.nextArrangement": { label: "Panes: the next existing arrangement" },
  "pane.prevArrangement": { label: "Panes: the previous existing arrangement" },
  "pane.lastArrangement": { label: "Panes: the last-used arrangement" },
  // SPR-01 M4 (R8/R9) + M5 (R12/R13): the resize mode and direct chords,
  // the second fullscreen level, and close-with-focus-return.
  "pane.resizeMode": { label: "Panes: resize mode (h/l width · j/k height · Enter commits · Esc restores)" },
  "pane.resizeNarrower": { label: "Panes: resize the focused pane 100 px narrower" },
  "pane.resizeWider": { label: "Panes: resize the focused pane 100 px wider" },
  "pane.resizeShorter": { label: "Panes: resize the focused pane 100 px shorter" },
  "pane.resizeTaller": { label: "Panes: resize the focused pane 100 px taller" },
  "pane.maximize": { label: "Panes: maximize the focused pane (keeps the rail and strip)" },
  "pane.close": { label: "Panes: close the focused pane (focus returns to the previous pane)" },
  "pane.fullscreen": { label: "Pane: fullscreen the focused pane (toggle)" },
  "layout.togglePreset": { label: PANE_FLOW_ON ? "Layout: horizontal ⇄ tiled" : "Layout: cockpit inset ⇄ docked" },
  "tab.next": { label: "Tab: next tab in the focused pane" },
  "tab.prev": { label: "Tab: previous tab in the focused pane" },
  "tab.new": { label: "Tab: new tab (picker)" },
  "tab.parent": { label: "Tab: up to the parent tab" },
  "tab.visitChild": { label: "Tab: down to the last-visited child tab" },
  "tab.close": { label: "Tab: close the focused pane's active tab (on the left, with its branches)" },
  "tab.reopen": { label: "Tab: reopen the last closed tab in the focused pane" },
  "tab.treeToggle": { label: "Tab: toggle the tab tree panel" },
  "project.select": { label: "Project: choose the account project" },
  "switcher.open": { label: "Switcher: open panes, windows and tabs (in:open)" },
  "inbox.toggle": { label: "Attention inbox" },
  "reader.tocToggle": { label: "Reader: show or hide the contents" },
  "door.research": { label: "Research", productId: "research", route: "/" },
  "door.read": { label: "Read", productId: "read", route: "/library" },
  "door.write": { label: "Write", productId: "write", route: "/write" },
  "door.speak": { label: "Speak", productId: "speak", route: "/speak" },
  "door.home": { label: "Home", productId: "home", route: "/home" },
  "door.more": { label: "More (all products)", productId: "more" },
  "door.researchHome": {
    label: "Research home",
    productId: "research",
    actionId: "new",
    route: "/",
  },
  "door.readLibrary": {
    label: "Read · the library",
    productId: "read",
    actionId: "library",
    route: "/library",
  },
} as const satisfies Record<string, ActionMeta>;

export type ActionId = keyof typeof ACTIONS;

/** Which SPR-08 table bindings.ts republishes a legacy row in. */
export type Spr08Kind = "builtin" | "product" | "subaction";

interface KeymapBinding {
  id: string;
  action: ActionId;
  prefixKey?: string;
  chord?: string;
  scope: KeymapScope;
  origin: KeymapOrigin;
  decision?: string;
  platforms?: readonly Platform[];
  spr08?: Spr08Kind;
}

export type KeymapRow = KeymapBinding & (
  | { status?: "implemented" }
  | { status: "unimplemented"; blockedBy: string }
);

const D = KEYMAP_DECISION;
const FLOW_DECISION = D + "; specs/codex-design-takeover-20260927/horizontal-pane-flow-20261002/contract.md (U1 cb8f0dd8)";

// ── SPR-01 M6 (R11): numbered arrangements 1–0 per project ──────────────
// The Omarchy mapping (refs/omarchy-herdr.md A2): prefix+digit and
// ctrl+alt+digit JUMP to arrangement N (SUPER+N); prefix+shift+digit and
// ctrl+alt+shift+digit MOVE the focused pane into arrangement N and follow
// (SUPER+SHIFT+N); prefix+tab / prefix+shift+tab cycle the EXISTING
// arrangements (SUPER+TAB, empty slots skip); prefix+ctrl+tab is the
// last-used one (SUPER+CTRL+TAB). Digit 0 is slot 10, Omarchy's ordering.
// Decision (the page's, recorded with its reconsider clause): prefix+digit
// is an arrangement jump, NOT herdr's tab jump — tabs keep n/p.
const M6_DECISION = "specs/antiek-keyboard-panes-agents-20261007/sprint-01-leader-key-tiling.html M6 (R11): prefix+digit is an arrangement jump, not herdr's tab jump (tabs keep n/p)";
const M6_BLOCKED = "antiek.flag.pane.flow (SPR-01 M6: arrangements exist only in flow mode)";

/** slot key → the two per-slot actions (literal, so ActionId stays exact).
 *  Exported: the dispatcher's handlers derive from the same table, so a
 *  key and its handler can never drift apart. */
export const ARRANGEMENT_KEY_ACTIONS = [
  { key: "1", jump: "pane.arrangement1", move: "pane.moveToArrangement1" },
  { key: "2", jump: "pane.arrangement2", move: "pane.moveToArrangement2" },
  { key: "3", jump: "pane.arrangement3", move: "pane.moveToArrangement3" },
  { key: "4", jump: "pane.arrangement4", move: "pane.moveToArrangement4" },
  { key: "5", jump: "pane.arrangement5", move: "pane.moveToArrangement5" },
  { key: "6", jump: "pane.arrangement6", move: "pane.moveToArrangement6" },
  { key: "7", jump: "pane.arrangement7", move: "pane.moveToArrangement7" },
  { key: "8", jump: "pane.arrangement8", move: "pane.moveToArrangement8" },
  { key: "9", jump: "pane.arrangement9", move: "pane.moveToArrangement9" },
  { key: "0", jump: "pane.arrangement10", move: "pane.moveToArrangement10" },
] as const;

/**
 * The 43 arrangement rows, one table for both worlds: implemented with the
 * flag on, declared pending on it with the flag off (the reorder rows'
 * precedent — the sheet says why and the dispatcher binds nothing). The
 * rows own 1–9 / ctrl+alt+1–9 in BOTH variants, so RESERVED_FOR_LATER drops
 * them unconditionally; 0 and the shift/tab forms were never reserved.
 */
function arrangementRows(implemented: boolean): KeymapRow[] {
  const row = (binding: KeymapBinding): KeymapRow =>
    implemented
      ? { ...binding }
      : { ...binding, status: "unimplemented", blockedBy: M6_BLOCKED };
  const rows: KeymapRow[] = [];
  for (const { key, jump, move } of ARRANGEMENT_KEY_ACTIONS) {
    rows.push(
      row({ id: `prefix-pane-arrangement-${key}`, action: jump, prefixKey: key, scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M6_DECISION }),
      row({ id: `chord-pane-arrangement-${key}`, action: jump, chord: `ctrl+alt+${key}`, scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M6_DECISION }),
      row({ id: `prefix-pane-move-arrangement-${key}`, action: move, prefixKey: `shift+${key}`, scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M6_DECISION }),
      row({ id: `chord-pane-move-arrangement-${key}`, action: move, chord: `ctrl+alt+shift+${key}`, scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M6_DECISION }),
    );
  }
  rows.push(
    row({ id: "prefix-pane-arrangement-next", action: "pane.nextArrangement", prefixKey: "tab", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M6_DECISION }),
    row({ id: "prefix-pane-arrangement-prev", action: "pane.prevArrangement", prefixKey: "shift+tab", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M6_DECISION }),
    row({ id: "prefix-pane-arrangement-last", action: "pane.lastArrangement", prefixKey: "ctrl+tab", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M6_DECISION }),
  );
  return rows;
}

// ── SPR-01 M4/M5: resize (R8/R9), maximize (R12), close (R13) ───────────
// M4: prefix+r enters the modal RESIZE mode (the herdr binding; r leaves
// RESERVED_FOR_LATER in the same diff — ctrl+alt+r stays held for its later
// sprint). The direct chords are ctrl+alt+- / ctrl+alt+= for width, with
// shift for height (Omarchy SUPER+- / SUPER+=); Omarchy's ALT 25 px and
// CTRL 300 px granularities are deliberately NOT added — ctrl+alt+shift is
// the last free modifier in this family and the page says so.
// M5: pane.maximize is fullscreen level 2 (Omarchy SUPER+ALT+F "full
// width": the work area edge to edge, rail and strip kept);
// content-fullscreen (SUPER+CTRL+F) is per-host and OUT of scope (the
// page's). pane.close is herdr's close-pane, with focus returning per R13.
const M4_M5_DECISION = "specs/antiek-keyboard-panes-agents-20261007/sprint-01-leader-key-tiling.html M4/M5 (R8/R9, R12/R13); Omarchy ALT/CTRL resize granularities deliberately not added (ctrl+alt+shift is the last free modifier)";
const M4_M5_BLOCKED = "antiek.flag.pane.flow (SPR-01 M4/M5: the flow pane model owns resize, maximize and pane close)";

function paneModeRows(implemented: boolean): KeymapRow[] {
  const row = (binding: KeymapBinding): KeymapRow =>
    implemented
      ? { ...binding }
      : { ...binding, status: "unimplemented", blockedBy: M4_M5_BLOCKED };
  return [
    row({ id: "prefix-pane-resize-mode", action: "pane.resizeMode", prefixKey: "r", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
    row({ id: "chord-pane-resize-narrower", action: "pane.resizeNarrower", chord: "ctrl+alt+-", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
    row({ id: "chord-pane-resize-wider", action: "pane.resizeWider", chord: "ctrl+alt+=", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
    row({ id: "chord-pane-resize-shorter", action: "pane.resizeShorter", chord: "ctrl+alt+shift+-", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
    row({ id: "chord-pane-resize-taller", action: "pane.resizeTaller", chord: "ctrl+alt+shift+=", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
    row({ id: "prefix-pane-maximize", action: "pane.maximize", prefixKey: "shift+f", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
    row({ id: "chord-pane-maximize", action: "pane.maximize", chord: "ctrl+alt+shift+f", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
    row({ id: "prefix-pane-close", action: "pane.close", prefixKey: "x", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
    row({ id: "chord-pane-close", action: "pane.close", chord: "ctrl+alt+x", scope: "outside-text", origin: "lane-Sweep-SPR-01", decision: M4_M5_DECISION }),
  ];
}

const LEGACY_PANE_ROWS: readonly KeymapRow[] = [
  { id: "prefix-pane-left", action: "pane.focusLeft", status: "implemented", prefixKey: "h", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-pane-left", action: "pane.focusLeft", status: "implemented", chord: "ctrl+alt+h", scope: "anywhere", origin: "D2", decision: D },
  { id: "prefix-pane-right", action: "pane.focusRight", status: "implemented", prefixKey: "l", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-pane-right", action: "pane.focusRight", status: "implemented", chord: "ctrl+alt+l", scope: "anywhere", origin: "D2", decision: D },
  { id: "prefix-pane-full", action: "pane.fullscreen", status: "implemented", prefixKey: "f", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-pane-full", action: "pane.fullscreen", status: "implemented", chord: "ctrl+alt+f", scope: "anywhere", origin: "D2", decision: D },
  // The stored preset defaults to DOCKED -- "a stored preset never surprises an
  // operator who never chose one" (workspace/persistence.ts) -- so this is not a
  // rarely-needed toggle but the key that brings the cockpit in. It sits behind
  // prefix+shift+i with no chord, and i stays the inbox's.
  { id: "prefix-layout-preset", action: "layout.togglePreset", status: "implemented", prefixKey: "shift+i", scope: "outside-text", origin: "D2", decision: D },
  // The reorder actions exist in ACTIONS (the ActionId type is static); with
  // the flag off they are declared pending on it — unimplemented rows on keys
  // main does not use, so the sheet says why and the dispatcher binds nothing.
  { id: "prefix-pane-reorder-left", action: "pane.reorderLeft", status: "unimplemented", blockedBy: "antiek.flag.pane.flow (SPR-01 M1 landing; flipped in SPR-05)", prefixKey: "shift+arrowleft", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "prefix-pane-reorder-right", action: "pane.reorderRight", status: "unimplemented", blockedBy: "antiek.flag.pane.flow (SPR-01 M1 landing; flipped in SPR-05)", prefixKey: "shift+arrowright", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  // The arrangement rows occupy their keys in both worlds (below).
  ...arrangementRows(false),
  ...paneModeRows(false),
];
const FLOW_PANE_ROWS: readonly KeymapRow[] = [
  { id: "prefix-pane-left", action: "pane.focusLeft", status: "implemented", prefixKey: "h", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-pane-left", action: "pane.focusLeft", status: "implemented", chord: "ctrl+alt+h", scope: "anywhere", origin: "D2", decision: D },
  { id: "prefix-pane-right", action: "pane.focusRight", status: "implemented", prefixKey: "l", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-pane-right", action: "pane.focusRight", status: "implemented", chord: "ctrl+alt+arrowright", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "chord-pane-left-arrow", action: "pane.focusLeft", status: "implemented", chord: "ctrl+alt+arrowleft", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "prefix-pane-left-arrow", action: "pane.focusLeft", status: "implemented", prefixKey: "arrowleft", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "prefix-pane-right-arrow", action: "pane.focusRight", status: "implemented", prefixKey: "arrowright", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "chord-pane-reorder-left", action: "pane.reorderLeft", status: "implemented", chord: "ctrl+alt+shift+arrowleft", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "chord-pane-reorder-right", action: "pane.reorderRight", status: "implemented", chord: "ctrl+alt+shift+arrowright", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "prefix-pane-reorder-left", action: "pane.reorderLeft", status: "implemented", prefixKey: "shift+arrowleft", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "prefix-pane-reorder-right", action: "pane.reorderRight", status: "implemented", prefixKey: "shift+arrowright", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  { id: "prefix-pane-full", action: "pane.fullscreen", status: "implemented", prefixKey: "f", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-pane-full", action: "pane.fullscreen", status: "implemented", chord: "ctrl+alt+f", scope: "anywhere", origin: "D2", decision: D },
  // L switches the connected hosts between horizontal flow and tiles.
  // Retain prefix+shift+i; i stays the inbox's.
  { id: "prefix-layout-preset", action: "layout.togglePreset", status: "implemented", prefixKey: "shift+i", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-layout-preset", action: "layout.togglePreset", status: "implemented", chord: "ctrl+alt+l", scope: "outside-text", origin: "D2", decision: FLOW_DECISION },
  // SPR-01 M6: the numbered arrangement rows (implemented).
  ...arrangementRows(true),
  // SPR-01 M4/M5: resize mode + direct chords, maximize, close.
  ...paneModeRows(true),
];


export const KEYMAP: readonly KeymapRow[] = [
  // ── legacy-SPR-08: the ⌘ scheme, unchanged keys ─────────────────────
  { id: "palette", action: "palette.toggle", status: "implemented", chord: "mod+k", scope: "anywhere", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "palette-alt", action: "palette.toggle", status: "implemented", chord: "mod+shift+p", scope: "anywhere", origin: "legacy-SPR-08", spr08: "builtin" },
  // Mac only: elsewhere "mod" is Ctrl, and ctrl+b is the prefix. There the
  // same action is prefix+b or ctrl+alt+b (rows below).
  { id: "projecttree", action: "projecttree.toggle", status: "implemented", chord: "mod+b", scope: "outside-text", origin: "legacy-SPR-08", platforms: ["mac"], spr08: "builtin" },
  { id: "aisidecar", action: "aisidecar.toggle", status: "implemented", chord: "mod+/", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "cycle-prev", action: "panel.focusPrev", status: "implemented", chord: "mod+[", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "cycle-next", action: "panel.focusNext", status: "implemented", chord: "mod+]", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "close-float", action: "panel.closeFloating", status: "implemented", chord: "mod+w", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "help", action: "keysheet.toggle", status: "implemented", chord: "?", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "prod-research", action: "door.research", status: "implemented", chord: "mod+j", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-read", action: "door.read", status: "implemented", chord: "mod+e", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-write", action: "door.write", status: "implemented", chord: "mod+y", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-speak", action: "door.speak", status: "implemented", chord: "mod+u", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-home", action: "door.home", status: "implemented", chord: "mod+o", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-more", action: "door.more", status: "implemented", chord: "mod+i", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "sub-research-new", action: "door.researchHome", status: "implemented", chord: "mod+g", scope: "outside-text", origin: "legacy-SPR-08", spr08: "subaction" },
  { id: "sub-read-library", action: "door.readLibrary", status: "implemented", chord: "mod+;", scope: "outside-text", origin: "legacy-SPR-08", spr08: "subaction" },

  // ── the prefix (herdr's defaults for the same meanings, adopted by D2) ──
  { id: "prefix-goto", action: "palette.toggle", status: "implemented", prefixKey: "g", scope: "outside-text", origin: "herdr-default", decision: D },
  { id: "prefix-help", action: "keysheet.toggle", status: "implemented", prefixKey: "?", scope: "outside-text", origin: "herdr-default", decision: D },
  { id: "prefix-sidebar", action: "projecttree.toggle", status: "implemented", prefixKey: "b", scope: "outside-text", origin: "herdr-default", decision: D },

  // ── D2 direct chords: every prefix action also has a one-step key ──────
  { id: "chord-sidebar", action: "projecttree.toggle", status: "implemented", chord: "ctrl+alt+b", scope: "anywhere", origin: "D2", decision: D },

  // ── D2 cockpit pane keys (C3, 2026-09-24): prefix twin + chord twin ────
  // h/l are herdr's pane-focus keys; f is fullscreen (Omarchy's gesture).
  // Never Cmd+Left/Right/F: the browser owns those (history, find).
  ...(PANE_FLOW_ON ? FLOW_PANE_ROWS : LEGACY_PANE_ROWS),

  // ── D2 tab keys (lane-A cockpit decision, 2026-09-26) ─────────────────
  // n/p + ctrl+alt+]/[ are herdr's next/previous tab, and herdr's tabs
  // belong to their pane: they cycle the FOCUSED pane's tabs (left: the
  // document tabs' siblings; right: the agent tabs, or the outline's block
  // tabs in writing). With neither pane focused they act on the left, where
  // the core material lives. One muscle memory, so no second pair exists.
  { id: "prefix-tab-next", action: "tab.next", status: "implemented", prefixKey: "n", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-tab-next", action: "tab.next", status: "implemented", chord: "ctrl+alt+]", scope: "anywhere", origin: "D2", decision: D },
  { id: "prefix-tab-prev", action: "tab.prev", status: "implemented", prefixKey: "p", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-tab-prev", action: "tab.prev", status: "implemented", chord: "ctrl+alt+[", scope: "anywhere", origin: "D2", decision: D },
  // c is "new tab": it opens the picker (a document or an investigation as
  // a fresh root tab in its own mothership's tree; workspace/newTab.ts).
  { id: "prefix-tab-new", action: "tab.new", status: "implemented", prefixKey: "c", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-tab-new", action: "tab.new", status: "implemented", chord: "ctrl+alt+c", scope: "anywhere", origin: "D2", decision: D },
  // Branch-tree keys (DESIGN-MODEL §2a). ctrl+alt+u collides with Konsole
  // only inside Konsole's own window, so it never reaches a browser.
  { id: "prefix-tab-parent", action: "tab.parent", status: "implemented", prefixKey: "u", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-tab-parent", action: "tab.parent", status: "implemented", chord: "ctrl+alt+u", scope: "anywhere", origin: "D2", decision: D },
  { id: "prefix-tab-child", action: "tab.visitChild", status: "implemented", prefixKey: "o", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-tab-child", action: "tab.visitChild", status: "implemented", chord: "ctrl+alt+o", scope: "anywhere", origin: "D2", decision: D },
  { id: "prefix-tab-tree", action: "tab.treeToggle", status: "implemented", prefixKey: "t", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-tab-tree", action: "tab.treeToggle", status: "implemented", chord: "ctrl+alt+y", scope: "anywhere", origin: "D2", decision: D },
  // Close is destructive, so it stays behind the prefix with no chord. It
  // closes the tab and its branches (§2a's default), held 10 s behind the
  // toast's Undo.
  { id: "prefix-tab-close", action: "tab.close", status: "implemented", prefixKey: "shift+x", scope: "outside-text", origin: "D2", decision: D },
  // The keyboard's undo for a close (browser muscle memory: ⌘⇧T). Inside the
  // 10 s hold it undoes the close; after it, it restores the focused pane's
  // most recently closed tab. No chord, like close.
  { id: "prefix-tab-reopen", action: "tab.reopen", status: "implemented", prefixKey: "shift+t", scope: "outside-text", origin: "D2", decision: D },

  // ── The reader's contents (lane A B2): in a narrow cockpit pane the TOC
  // column folds away (a container query), and this brings it back in the
  // pane. shift+c, beside c (new tab), for "contents".
  { id: "prefix-reader-toc", action: "reader.tocToggle", status: "implemented", prefixKey: "shift+c", scope: "outside-text", origin: "lane-A-proposed", decision: "lane A proposal 2026-09-27 (A1c), pending ratification" },

  // ── D2 attention inbox (D4): declared unimplemented; no handler is installed ─
  { id: "prefix-inbox", action: "inbox.toggle", status: "unimplemented", blockedBy: "MS-03 M7; THREAD-CONTRACT §1.5 inbox delivery after created-owner authority acceptance", prefixKey: "i", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-inbox", action: "inbox.toggle", status: "unimplemented", blockedBy: "MS-03 M7; THREAD-CONTRACT §1.5 inbox delivery after created-owner authority acceptance", chord: "ctrl+alt+i", scope: "anywhere", origin: "D2", decision: D },

  // ── The project level (the D2 keyboard's missing second level) ────────
  // shift+p, beside p (previous tab): the tabs live IN the project, so the
  // project's key is the tab key shifted. prefix+p itself is taken and
  // ctrl+alt+p is free on every platform the D2 table maps. Proposed with
  // the implementation, pending ratification into the decision record.
  { id: "prefix-project-select", action: "project.select", status: "implemented", prefixKey: "shift+p", scope: "outside-text", origin: "lane-A-proposed", decision: "lane D2 keyboard implementation 2026-10-03, pending ratification" },
  { id: "chord-project-select", action: "project.select", status: "implemented", chord: "ctrl+alt+p", scope: "anywhere", origin: "lane-A-proposed", decision: "lane D2 keyboard implementation 2026-10-03, pending ratification" },
  // SPR-02 M5 — the Switcher narrowed to the Open section. shift+o because
  // prefix+o is tab.visitChild (herdr's "go to the toast" is a later unit).
  { id: "prefix-switcher-open", action: "switcher.open", status: "implemented", prefixKey: "shift+o", scope: "outside-text", origin: "lane-Sweep-SPR-02", decision: "SPR-02 M5 — specs/antiek-keyboard-panes-agents-20261007/sprint-02-launcher.html (herdr goto picker: the Switcher opened already narrowed to open panes/windows/tabs)" },
  { id: "chord-switcher-open", action: "switcher.open", status: "implemented", chord: "ctrl+alt+shift+o", scope: "anywhere", origin: "lane-Sweep-SPR-02", decision: "SPR-02 M5 — specs/antiek-keyboard-panes-agents-20261007/sprint-02-launcher.html (herdr goto picker: the Switcher opened already narrowed to open panes/windows/tabs)" },
];

/**
 * Keys the D2 table (DESIGN-MODEL §2, §2a) gives to MS-03/MS-04 surfaces that
 * do not exist yet: numbered tabs, workstations, motherships, the companion
 * rail, islands. No row may take one of them for another meaning; the
 * sprint that builds the surface moves the key into KEYMAP and deletes it
 * here. (The attention inbox has explicitly unimplemented rows and no handler;
 * the sheet derives that status from this table.)
 * ctrl+alt+a is a KDE Plasma global grab; DESIGN-MODEL §2 keeps it, because
 * prefix+a always works and the operator's platforms do not grab it.
 * SPR-01 M6 took 1–9 and ctrl+alt+1–9 for the numbered arrangements (R11);
 * the arrangement rows own them in both flag worlds. Digit 0 was never
 * reserved and is theirs too. SPR-01 M4 took prefix+r for the RESIZE mode;
 * ctrl+alt+r stays held for its later sprint.
 */
export const RESERVED_FOR_LATER = {
  prefixKeys: [
    "w", "shift+n", "m", "shift+m",
    "a",
  ],
  chords: [
    "ctrl+alt+w",
    "ctrl+alt+shift+]", "ctrl+alt+shift+[", "ctrl+alt+m",
    "ctrl+alt+r", "ctrl+alt+a",
  ],
} as const;

// ─────────────────────────────────────────────────────────────────────
// Platform + prefix configuration
// ─────────────────────────────────────────────────────────────────────

export function currentPlatform(): Platform {
  if (typeof navigator === "undefined") return "mac";
  return /mac|iphone|ipad|ipod/i.test(navigator.platform || navigator.userAgent) ? "mac" : "other";
}

export function isActiveOn(row: KeymapRow, platform: Platform): boolean {
  return !row.platforms || row.platforms.includes(platform);
}

export const DEFAULT_PREFIX = "ctrl+b";
const PREFIX_STORAGE_KEY = "antiek.keymap.prefix";

/** The prefix in force: the operator's saved choice, else ctrl+b. */
export function readPrefix(): string {
  try {
    const saved = window.localStorage.getItem(PREFIX_STORAGE_KEY);
    // The read runs the same full check as setPrefix. Storage outlives the
    // table: a prefix saved before a chord was added (say ctrl+alt+b) would
    // otherwise collide with that chord (carrier critic r1).
    if (saved && isUsablePrefix(saved)) return saved;
  } catch {
    // storage unavailable: the default stands
  }
  return DEFAULT_PREFIX;
}

/** Save a different prefix (null restores ctrl+b). Returns false and saves
 *  nothing when the combo cannot be a prefix. */
export function setPrefix(spec: string | null): boolean {
  if (spec !== null && !isUsablePrefix(spec)) return false;
  try {
    if (spec === null) window.localStorage.removeItem(PREFIX_STORAGE_KEY);
    else window.localStorage.setItem(PREFIX_STORAGE_KEY, normalizeCombo(spec));
  } catch {
    return false;
  }
  return true;
}

/**
 * Can `spec` be the prefix? It needs ctrl: a bare or shift-only key would eat
 * typing, plain alt composes characters on macOS, and a ⌘ combo would take
 * a legacy row. And it must not be any row's key on ANY platform, where
 * "mod" is ⌘ on a Mac and Ctrl elsewhere: ctrl+k is ⌘K's key off the Mac,
 * so it is refused (critic r1). ctrl+b, the default, is free on both: its
 * only neighbour, the ⌘B row, exists on the Mac alone.
 */
export function isUsablePrefix(spec: string): boolean {
  const c = parseCombo(spec);
  if (!c.key || c.mod || c.meta || !c.ctrl) return false;
  return (["mac", "other"] as const).every((platform) => {
    const phys = physicalKey(c, platform);
    return !KEYMAP.some(
      (r) => r.chord && isActiveOn(r, platform) && physicalKey(parseCombo(r.chord), platform) === phys,
    );
  });
}

// ─────────────────────────────────────────────────────────────────────
// Combo parsing and matching
// ─────────────────────────────────────────────────────────────────────

export interface Combo {
  mod: boolean;
  ctrl: boolean;
  alt: boolean;
  shift: boolean;
  meta: boolean;
  /** Lower-case key: "k", "1", "[", "?", "escape". */
  key: string;
}

export const MODIFIER_TOKENS = ["mod", "ctrl", "alt", "shift", "meta"] as const;

export function parseCombo(spec: string): Combo {
  const parts = spec.trim().toLowerCase().split("+").map((p) => p.trim());
  // "?" and other lone keys; a trailing "+" key would appear as "".
  const key = parts.length === 1 ? parts[0] : parts[parts.length - 1];
  const mods = new Set(parts.slice(0, -1));
  return {
    mod: mods.has("mod"),
    ctrl: mods.has("ctrl"),
    alt: mods.has("alt"),
    shift: mods.has("shift"),
    meta: mods.has("meta"),
    key,
  };
}

/** Canonical spec: modifiers in a fixed order, key last. */
export function normalizeCombo(spec: string): string {
  const c = parseCombo(spec);
  const mods = MODIFIER_TOKENS.filter((m) => c[m]);
  return [...mods, c.key].join("+");
}

// The punctuation keys the ctrl+alt family can use (DESIGN-MODEL §2 uses the
// brackets). Add a code here when a row needs another physical key.
const CODE_KEYS: Record<string, string> = {
  BracketLeft: "[",
  BracketRight: "]",
  Slash: "/",
  Semicolon: ";",
  Comma: ",",
  Period: ".",
  Minus: "-",
  Equal: "=",
  Quote: "'",
  ArrowLeft: "arrowleft",
  ArrowRight: "arrowright",
};

/** The unshifted key printed on the physical key `code` (US layout), or "". */
export function codeToKey(code: string): string {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);
  return CODE_KEYS[code] ?? "";
}

/** The key an event names: e.key lower-cased, falling back to the physical
 *  key when a non-Latin layout reports another script's letter. */
export function logicalKey(e: KeyboardEvent): string {
  const k = e.key ?? "";
  if (k.length === 1 && k.charCodeAt(0) > 127) return codeToKey(e.code ?? "") || k.toLowerCase();
  return k.toLowerCase();
}

export function isLoneModifier(e: KeyboardEvent): boolean {
  return ["Shift", "Control", "Alt", "Meta", "AltGraph", "CapsLock"].includes(e.key);
}

function altGraph(e: KeyboardEvent): boolean {
  return typeof e.getModifierState === "function" && e.getModifierState("AltGraph");
}

/**
 * Would keydown `e` type something into a focused text surface? Inside text,
 * a ctrl+alt chord fires only when the key typed nothing but its own physical
 * letter: e.key is one character and equals the key printed on e.code. Any
 * other key belongs to the field. eventMatchesCombo already refuses a press
 * that reports AltGraph; this rule covers the presses that do not
 * (carrier critic r1 and r2).
 *  - AltGr layouts: Windows treats left ctrl+alt as AltGr (Hungarian and
 *    Czech ctrl+alt+b is "{"), sometimes without reporting AltGraph.
 *  - macOS: Chromium lets Control+Option insert printable characters
 *    (editing_behavior.cc), and a cancelled keydown suppresses its input
 *    (UI Events). So an Option glyph such as "∫" is the field's too. On a
 *    Mac, inside text, the chords therefore do not fire; the prefix works
 *    outside text, and so do the chords.
 *  - Dead keys ("Dead"), IME processing ("Process"), "Unidentified" and
 *    every other named key are never a chord inside text.
 */
export function chordTypesText(e: KeyboardEvent): boolean {
  if (e.isComposing) return true;
  return !(e.key.length === 1 && e.key.toLowerCase() === codeToKey(e.code ?? ""));
}

/**
 * Does keydown `e` press `spec`? One matcher for the three kinds of key:
 *  - a ctrl+alt chord matches the PHYSICAL key (e.code), never the character
 *    the OS composed, and never an AltGr press;
 *  - "mod" (the SPR-08 ⌘ rows) accepts ⌘ or Ctrl;
 *  - a lone non-letter ("?", "1") ignores shift, because the character
 *    already carries it ("?" is shift+/);
 *  - a ctrl combo (the prefix) also matches by physical key, so it survives
 *    a non-Latin layout.
 * Used for direct keys, for the prefix, and for the key after the prefix.
 */
export function eventMatchesCombo(e: KeyboardEvent, spec: string): boolean {
  const c = parseCombo(spec);
  if (c.mod ? !(e.metaKey || e.ctrlKey) : e.ctrlKey !== c.ctrl || e.metaKey !== c.meta) return false;
  if (e.altKey !== c.alt) return false;
  const code = codeToKey(e.code ?? "");
  if (c.alt) return !altGraph(e) && e.shiftKey === c.shift && code === c.key;
  if (c.key === "arrowleft" || c.key === "arrowright") return !altGraph(e) && e.shiftKey === c.shift && code === c.key;
  // SPR-01 M6 rows: digits distinguish shift (prefix+1 jumps, prefix+shift+1
  // moves), matched on the physical Digit code so a shifted glyph ("!") still
  // resolves; Tab matches its named key with the shift distinction the
  // raw-key branch below deliberately skips for punctuation.
  if (/^[0-9]$/.test(c.key)) return e.shiftKey === c.shift && (e.key === c.key || code === c.key);
  if (c.key === "tab") return e.shiftKey === c.shift && (e.key === "Tab" || e.code === "Tab");
  if (!c.mod && !c.ctrl && !c.meta && !/^[a-z]$/.test(c.key)) return e.key === c.key;
  return e.shiftKey === c.shift && (logicalKey(e) === c.key || (c.ctrl && code === c.key));
}

/** The key a combo resolves to on `platform`, for duplicate detection. "mod"
 *  resolves to the platform's primary modifier. */
export function physicalKey(c: Combo, platform: Platform): string {
  const ctrl = c.ctrl || (c.mod && platform === "other");
  const meta = c.meta || (c.mod && platform === "mac");
  return `${ctrl ? "ctrl+" : ""}${c.alt ? "alt+" : ""}${c.shift ? "shift+" : ""}${meta ? "meta+" : ""}${c.key}`;
}

// ─────────────────────────────────────────────────────────────────────
// Integrity: the table-driven guard (keymap.test.ts runs it)
// ─────────────────────────────────────────────────────────────────────

export interface KeymapProblem {
  kind:
    | "duplicate"
    | "missing-handler"
    | "unexpected-handler"
    | "inconsistent-status"
    | "missing-scenario"
    | "unexercised-row"
    | "missing-sheet-row"
    | "unexpected-sheet-row"
    | "missing-decision"
    | "plain-alt-chord"
    | "prefix-scope"
    | "reserved-key";
  row: string;
  detail: string;
}

/**
 * Every way the table can be wrong, per platform:
 *  - two rows (or a row and the prefix) answer to the same physical key;
 *  - a row's action has no handler in the dispatcher;
 *  - a herdr-default or D2 row does not cite the decision record;
 *  - a chord uses alt without ctrl (macOS composes it into a character);
 *  - a prefix row claims scope "anywhere" (the prefix never arms in text);
 *  - a row takes a key the D2 table reserves for a later sprint.
 */
export function validateKeymap(
  rows: readonly KeymapRow[],
  handlerIds: readonly string[],
  opts: {
    prefix?: string;
    platforms?: readonly Platform[];
    coverage?: {
      scenarios: readonly string[];
      exercisedRows: readonly string[];
      sheetRows: readonly string[];
    };
  } = {},
): KeymapProblem[] {
  const problems: KeymapProblem[] = [];
  const prefix = opts.prefix ?? DEFAULT_PREFIX;
  const handlers = new Set(handlerIds);
  const reservedPrefix = new Set<string>(RESERVED_FOR_LATER.prefixKeys);
  const reservedChord = new Set<string>(RESERVED_FOR_LATER.chords.map(normalizeCombo));

  for (const r of rows) {
    if (r.status === "unimplemented") {
      if (handlers.has(r.action)) problems.push({ kind: "unexpected-handler", row: r.id, detail: `action ${r.action} declares unimplemented but has a handler` });
      if (!r.blockedBy.trim()) problems.push({ kind: "inconsistent-status", row: r.id, detail: `action ${r.action} declares unimplemented without a blocker` });
    } else if (!handlers.has(r.action)) {
      problems.push({ kind: "missing-handler", row: r.id, detail: `no handler for "${r.action}"` });
    }
    if (rows.some((alias) => alias.action === r.action && (alias.status ?? "implemented") !== (r.status ?? "implemented"))) {
      problems.push({ kind: "inconsistent-status", row: r.id, detail: `aliases disagree on status of ${r.action}` });
    }
    if ((r.origin === "D2" || r.origin === "herdr-default") && !r.decision?.includes("mothership-keys-herdr-prefix.md")) {
      problems.push({ kind: "missing-decision", row: r.id, detail: `${r.origin} row must cite the D2 decision record` });
    }
    if (r.chord) {
      const c = parseCombo(r.chord);
      if (c.alt && !c.ctrl) {
        problems.push({ kind: "plain-alt-chord", row: r.id, detail: `${r.chord}: plain alt composes characters on macOS` });
      }
      if (reservedChord.has(normalizeCombo(r.chord))) {
        problems.push({ kind: "reserved-key", row: r.id, detail: `${r.chord} is reserved for a later sprint` });
      }
    }
    if (r.prefixKey) {
      if (r.scope !== "outside-text") {
        problems.push({ kind: "prefix-scope", row: r.id, detail: "the prefix never arms inside text" });
      }
      if (reservedPrefix.has(normalizeCombo(r.prefixKey))) {
        problems.push({ kind: "reserved-key", row: r.id, detail: `prefix+${r.prefixKey} is reserved for a later sprint` });
      }
    }
  }

  if (opts.coverage) {
    const scenarios = new Set(opts.coverage.scenarios);
    const exercisedRows = new Set(opts.coverage.exercisedRows);
    const sheetRows = new Set(opts.coverage.sheetRows);
    const rowIds = new Set(rows.map((row) => row.id));
    for (const row of rows) {
      if (!scenarios.has(row.action)) problems.push({ kind: "missing-scenario", row: row.id, detail: `action ${row.action}: no executable scenario` });
      if (!exercisedRows.has(row.id)) problems.push({ kind: "unexercised-row", row: row.id, detail: `action ${row.action}: alias was not pressed` });
      if (!sheetRows.has(row.id)) problems.push({ kind: "missing-sheet-row", row: row.id, detail: `action ${row.action}: absent from rendered key sheet` });
    }
    for (const id of sheetRows) {
      if (!rowIds.has(id)) problems.push({ kind: "unexpected-sheet-row", row: id, detail: "rendered sheet advertises a row absent from KEYMAP" });
    }
  }

  for (const platform of opts.platforms ?? (["mac", "other"] as const)) {
    const owner = new Map<string, string>();
    owner.set(physicalKey(parseCombo(prefix), platform), "(the prefix)");
    const prefixOwner = new Map<string, string>();
    for (const r of rows) {
      if (!isActiveOn(r, platform)) continue;
      if (r.chord) {
        const phys = physicalKey(parseCombo(r.chord), platform);
        const prior = owner.get(phys);
        if (prior) {
          problems.push({ kind: "duplicate", row: r.id, detail: `${phys} on ${platform} is also ${prior}` });
        } else {
          owner.set(phys, r.id);
        }
      }
      if (r.prefixKey) {
        const k = normalizeCombo(r.prefixKey);
        const prior = prefixOwner.get(k);
        if (prior) {
          problems.push({ kind: "duplicate", row: r.id, detail: `prefix+${k} on ${platform} is also ${prior}` });
        } else {
          prefixOwner.set(k, r.id);
        }
      }
    }
  }
  return problems;
}
