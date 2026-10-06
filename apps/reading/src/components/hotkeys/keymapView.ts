/**
 * keymapView.ts — how the key sheet draws the keymap: task titles and one
 * keycap per key. Display only; the bindings live in keymap.ts. Kept apart
 * so it loads with the lazy key sheet, not in the entry chunk.
 */
import {
  MODIFIER_TOKENS,
  KEYMAP,
  currentPlatform,
  parseCombo,
  type ActionId,
  type KeymapTask,
  type Platform,
} from "./keymap";
import { LAYOUT_PRESET_DEFAULT } from "../../workspace/persistence";
import type { LayoutPreset } from "../../workspace/panel.types";

/** The key-sheet group of each action. */
export const TASK_OF: Record<ActionId, KeymapTask> = {
  "palette.toggle": "find",
  "keysheet.toggle": "help",
  "projecttree.toggle": "panels",
  "aisidecar.toggle": "panels",
  "panel.focusPrev": "panels",
  "panel.focusNext": "panels",
  "panel.closeFloating": "panels",
  "pane.focusLeft": "panels",
  "pane.focusRight": "panels",
  "pane.fullscreen": "panels",
  "layout.togglePreset": "panels",
  "tab.next": "panels",
  "tab.prev": "panels",
  "tab.new": "panels",
  "tab.parent": "panels",
  "tab.visitChild": "panels",
  "tab.close": "panels",
  "tab.reopen": "panels",
  "tab.treeToggle": "panels",
  "project.select": "find",
  "inbox.toggle": "panels",
  "reader.tocToggle": "panels",
  "door.research": "go",
  "door.read": "go",
  "door.write": "go",
  "door.speak": "go",
  "door.home": "go",
  "door.more": "go",
  "door.researchHome": "go",
  "door.readLibrary": "go",
};

/**
 * The key sheet's line for `layout.togglePreset`, as a FUNCTION of the preset a
 * workspace starts on.
 *
 * It is a function rather than a sentence because a sentence cannot be checked.
 * An earlier revision interpolated the constant into a literal and tested the
 * result with regexes; a critic defeated it by writing a false sentence that
 * never used the word the regex looked for - "a fresh workspace starts on the
 * two tall panes" names the inset without naming it. Equality against this
 * function is sound: the note must be exactly HELP(LAYOUT_PRESET_DEFAULT), so a
 * hand-written claim about a different preset cannot pass.
 */
export function layoutPresetHelp(defaultPreset: LayoutPreset): string {
  return `Switches between docked and the cockpit inset (two tall panes). A workspace that has never chosen one starts ${defaultPreset}; this key switches to the other layout.`;
}
/** A caveat the sheet shows under an action's label. */
export const NOTES: Partial<Record<ActionId, string>> = {
  "panel.closeFloating": "Only while a floating panel has focus; otherwise the browser closes the tab.",
  "pane.focusLeft": "On a narrow screen (768–1023 px) one pane shows at a time; this brings the left one on.",
  "pane.focusRight": "On a narrow screen (768–1023 px) one pane shows at a time; this brings the right one on.",
  "pane.fullscreen": "Esc or the same key restores both panes.",
  // The shipped copy said the cockpit was already the default while the reader
  // returned "docked". This is now the template applied to the real default, so
  // the note cannot describe a preset the code does not start on.
  "layout.togglePreset": layoutPresetHelp(LAYOUT_PRESET_DEFAULT),
  "tab.next":
    "Acts on the focused pane: document tabs on the left, agent tabs (block tabs when writing) on the right. With neither pane focused, the left. Wraps.",
  "tab.prev": "The same pane rule as the next tab.",
  "tab.new":
    "Opens the new-tab picker: a document or an investigation as a fresh top-level tab in its own tree. Picking one you already have open takes you back to that tab.",
  "tab.close":
    "Acts on the focused pane. On the left it closes the tab and everything branched from it; on the right, the agent tab (the agent itself is untouched). The pages it pointed at are untouched, and Undo stays in the toast for 10 seconds. To close only one tab and keep its branches, use Shift+Delete on its row in the tab tree.",
  "tab.reopen":
    "Within 10 seconds of a close it undoes it. After that it brings back the most recently closed tab of the focused pane, with its number.",
  "reader.tocToggle":
    "When the reader's pane is too narrow to keep the contents beside the text, this opens them over the page. Esc or a chapter closes them.",
  "project.select":
    "Opens the account projects from the registry and files your tabs under the one you pick; each project's tabs are its own. The sidebar's project row opens the same picker.",
  "inbox.toggle": "Not built yet: the key is kept for the attention inbox. Until it ships the key does nothing.",
};

/** Actions whose key is held for a surface that has not shipped: the sheet
 *  marks the row. These actions have no handler, and the dispatcher leaves
 *  their direct chords to the page. */
export const PENDING: ReadonlySet<ActionId> = new Set<ActionId>(KEYMAP.filter((row) => row.status === "unimplemented").map((row) => row.action));

export const TASK_TITLES: Record<KeymapTask, string> = {
  find: "Find and switch",
  go: "Go to",
  panels: "Panels",
  help: "Help",
};

const MAC_GLYPHS: Record<string, string> = { mod: "⌘", meta: "⌘", ctrl: "⌃", alt: "⌥", shift: "⇧" };
const OTHER_GLYPHS: Record<string, string> = { mod: "Ctrl", meta: "Win", ctrl: "Ctrl", alt: "Alt", shift: "Shift" };
const KEY_NAMES: Record<string, string> = {
  escape: "Esc",
  arrowleft: "←",
  arrowright: "→",
  arrowup: "↑",
  arrowdown: "↓",
  enter: "↵",
};

/** One label per key of a combo, for separate <kbd>s: "ctrl+alt+b" → ["⌃", "⌥", "B"]. */
export function comboParts(spec: string, platform: Platform = currentPlatform()): string[] {
  const c = parseCombo(spec);
  const glyphs = platform === "mac" ? MAC_GLYPHS : OTHER_GLYPHS;
  const mods = MODIFIER_TOKENS.filter((m) => c[m]).map((m) => glyphs[m]);
  const key = KEY_NAMES[c.key] ?? (c.key.length === 1 ? c.key.toUpperCase() : c.key);
  return [...mods, key];
}
