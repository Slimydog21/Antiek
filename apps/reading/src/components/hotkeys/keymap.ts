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

export type KeymapOrigin = "herdr-default" | "D2" | "legacy-SPR-08" | "lane-A-proposed" | "lane-Sweep-SPR-02";
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

export const ACTIONS = {
  "palette.toggle": { label: "Switcher (command palette)" },
  "keysheet.toggle": { label: "Key sheet (this list)" },
  "projecttree.toggle": { label: "Toggle the sidebar (project tree)" },
  "aisidecar.toggle": { label: "Toggle the AI sidecar" },
  "panel.focusPrev": { label: "Focus the previous panel" },
  "panel.focusNext": { label: "Focus the next panel" },
  "panel.closeFloating": { label: "Close the focused floating panel" },
  "pane.focusLeft": { label: "Pane: focus the left pane" },
  "pane.focusRight": { label: "Pane: focus the right pane" },
  "pane.fullscreen": { label: "Pane: fullscreen the focused pane (toggle)" },
  "layout.togglePreset": { label: "Layout: cockpit inset ⇄ docked" },
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
  "agent.openPane": { label: "Agent: open the project's agent pane (or focus its composer)" },
  "agents.gotoToast": { label: "Agents: go to the agent the toast is about" },
  "agents.goto": { label: "Agents: go to an agent (picker, filters by state)" },
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

  // ── SPR-10 agents (herdr B7 toast jump, B6 goto picker). herdr binds o and
  // g; here prefix+o is tab.visitChild (D2) and prefix+g is the Switcher, and
  // #3751 (SPR-02) holds the shifted twin shift+o / ctrl+alt+shift+o for
  // switcher.open. The toast key is therefore j, "jump to what the toast is
  // about" (herdr B7:379 "jumps"), shifted so a later pane.focusDown can keep
  // the plain letter; the picker is g shifted (the shift+p / shift+c
  // precedent). Both pending ratification; the sprint page's literal prefix+o
  // cannot be met while tab.visitChild owns it (INBOX 2026-10-07T23:06Z).
  { id: "prefix-agents-toast", action: "agents.gotoToast", status: "implemented", prefixKey: "shift+j", scope: "outside-text", origin: "lane-A-proposed", decision: "SPR-10 agent monitoring 2026-10-07T23:06Z (prefix+o is tab.visitChild, shift+o is #3751 switcher.open; j = jump), pending ratification" },
  { id: "chord-agents-toast", action: "agents.gotoToast", status: "implemented", chord: "ctrl+alt+shift+j", scope: "anywhere", origin: "lane-A-proposed", decision: "SPR-10 agent monitoring 2026-10-07T23:06Z, pending ratification" },
  { id: "prefix-agents-goto", action: "agents.goto", status: "implemented", prefixKey: "shift+g", scope: "outside-text", origin: "lane-A-proposed", decision: "SPR-10 agent monitoring 2026-10-07T23:06Z (prefix+g stays palette.toggle), pending ratification" },
  { id: "chord-agents-goto", action: "agents.goto", status: "implemented", chord: "ctrl+alt+g", scope: "anywhere", origin: "lane-A-proposed", decision: "SPR-10 agent monitoring 2026-10-07T23:06Z; the chord is what closes the picker from inside it (shortcuts.ts scopeAllows), pending ratification" },

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

  // ── SPR-07 the agent pane: prefix+a / ctrl+alt+a under D2's "a" ("ask about
  // this"; DESIGN-MODEL §2). ONE action: open-or-focus is idempotent (a
  // second press refocuses the composer, never a second tab). Handler:
  // shortcuts.ts openAgentPaneKey → agent/openAgentPane.ts (lazy); guard
  // scenario asserts the composer takes focus. A saved prefix of ctrl+alt+a
  // silently falls back to ctrl+b (readPrefix).
  { id: "prefix-agent-pane", action: "agent.openPane", status: "implemented", prefixKey: "a", scope: "outside-text", origin: "D2", decision: D },
  { id: "chord-agent-pane", action: "agent.openPane", status: "implemented", chord: "ctrl+alt+a", scope: "anywhere", origin: "D2", decision: D },
];

/**
 * Keys the D2 table (DESIGN-MODEL §2, §2a) gives to MS-03/MS-04 surfaces that
 * do not exist yet: numbered tabs, workstations, motherships, the companion
 * rail, islands. No row may take one of them for another meaning; the
 * sprint that builds the surface moves the key into KEYMAP and deletes it
 * here. (The attention inbox has explicitly unimplemented rows and no handler;
 * the sheet derives that status from this table.)
 * ctrl+alt+a is a KDE Plasma global grab; DESIGN-MODEL §2 keeps it, because
 * prefix+a always works and the operator's platforms do not grab it. SPR-07
 * moved a / ctrl+alt+a into KEYMAP (the agent pane; islands' "ask about
 * this" reading, handoff F8).
 */
export const RESERVED_FOR_LATER = {
  prefixKeys: [
    "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "w", "shift+n", "m", "shift+m",
    "r",
  ],
  chords: [
    "ctrl+alt+1", "ctrl+alt+2", "ctrl+alt+3", "ctrl+alt+4", "ctrl+alt+5",
    "ctrl+alt+6", "ctrl+alt+7", "ctrl+alt+8", "ctrl+alt+9",
    "ctrl+alt+w",
    "ctrl+alt+shift+]", "ctrl+alt+shift+[", "ctrl+alt+m",
    "ctrl+alt+r",
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
