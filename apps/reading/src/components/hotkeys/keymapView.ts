/**
 * keymapView.ts — how the key sheet draws the keymap: task titles and one
 * keycap per key. Display only; the bindings live in keymap.ts. Kept apart
 * so it loads with the lazy key sheet, not in the entry chunk.
 */
import {
  MODIFIER_TOKENS,
  currentPlatform,
  parseCombo,
  type ActionId,
  type KeymapTask,
  type Platform,
} from "./keymap";

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
  "tab.nextSibling": "panels",
  "tab.prevSibling": "panels",
  "tab.parent": "panels",
  "tab.visitChild": "panels",
  "tab.close": "panels",
  "tab.prune": "panels",
  "tab.treeToggle": "panels",
  "companion.nextTab": "panels",
  "companion.prevTab": "panels",
  "door.research": "go",
  "door.read": "go",
  "door.write": "go",
  "door.speak": "go",
  "door.home": "go",
  "door.more": "go",
  "door.researchHome": "go",
  "door.readLibrary": "go",
};

/** A caveat the sheet shows under an action's label. */
export const NOTES: Partial<Record<ActionId, string>> = {
  "panel.closeFloating": "Only while a floating panel has focus; otherwise the browser closes the tab.",
  "pane.fullscreen": "Esc or the same key restores both panes.",
  "layout.togglePreset": "The inset preset shows two tall panes over the scene; docked stays the default.",
  "companion.nextTab": "Cycles the companion's agent tabs (wraps); a no-op where the pane is not visible.",
  "tab.parent": "The ctrl+alt+u twin collides with Konsole's global on KDE — the browser may never see it there; prefix+u works everywhere.",
  "tab.close": "Closing is a view act (children lift into its place); the surface it pointed at is untouched. Undo is offered in the strip.",
  "tab.prune": "Closes the tab and its whole subtree (soft — recoverable from the strip's undo).",
};

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
