/**
 * keymap.ts — THE keymap. Every key the app answers to is a row in
 * {@link KEYMAP}; nothing else may define a binding.
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

export type KeymapOrigin = "herdr-default" | "D2" | "legacy-SPR-08";
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

export interface KeymapRow {
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

const D = KEYMAP_DECISION;

export const KEYMAP: readonly KeymapRow[] = [
  // ── legacy-SPR-08: the ⌘ scheme, unchanged keys ─────────────────────
  { id: "palette", action: "palette.toggle", chord: "mod+k", scope: "anywhere", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "palette-alt", action: "palette.toggle", chord: "mod+shift+p", scope: "anywhere", origin: "legacy-SPR-08", spr08: "builtin" },
  // Mac only: elsewhere "mod" is Ctrl, and ctrl+b is the prefix. There the
  // same action is prefix+b or ctrl+alt+b (rows below).
  { id: "projecttree", action: "projecttree.toggle", chord: "mod+b", scope: "outside-text", origin: "legacy-SPR-08", platforms: ["mac"], spr08: "builtin" },
  { id: "aisidecar", action: "aisidecar.toggle", chord: "mod+/", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "cycle-prev", action: "panel.focusPrev", chord: "mod+[", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "cycle-next", action: "panel.focusNext", chord: "mod+]", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "close-float", action: "panel.closeFloating", chord: "mod+w", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "help", action: "keysheet.toggle", chord: "?", scope: "outside-text", origin: "legacy-SPR-08", spr08: "builtin" },
  { id: "prod-research", action: "door.research", chord: "mod+j", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-read", action: "door.read", chord: "mod+e", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-write", action: "door.write", chord: "mod+y", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-speak", action: "door.speak", chord: "mod+u", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-home", action: "door.home", chord: "mod+o", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "prod-more", action: "door.more", chord: "mod+i", scope: "outside-text", origin: "legacy-SPR-08", spr08: "product" },
  { id: "sub-research-new", action: "door.researchHome", chord: "mod+g", scope: "outside-text", origin: "legacy-SPR-08", spr08: "subaction" },
  { id: "sub-read-library", action: "door.readLibrary", chord: "mod+;", scope: "outside-text", origin: "legacy-SPR-08", spr08: "subaction" },

  // ── the prefix (herdr's defaults for the same meanings, adopted by D2) ──
  { id: "prefix-goto", action: "palette.toggle", prefixKey: "g", scope: "outside-text", origin: "herdr-default", decision: D },
  { id: "prefix-help", action: "keysheet.toggle", prefixKey: "?", scope: "outside-text", origin: "herdr-default", decision: D },
  { id: "prefix-sidebar", action: "projecttree.toggle", prefixKey: "b", scope: "outside-text", origin: "herdr-default", decision: D },

  // ── D2 direct chords: every prefix action also has a one-step key ──────
  { id: "chord-sidebar", action: "projecttree.toggle", chord: "ctrl+alt+b", scope: "anywhere", origin: "D2", decision: D },
];

/**
 * Keys the D2 table (DESIGN-MODEL §2, §2a) gives to MS-03/MS-04 surfaces that
 * do not exist yet: tabs, workstations, motherships, the branch tree, the
 * inbox. No row may take one of them for another meaning; the sprint that
 * builds the surface moves the key into KEYMAP and deletes it here.
 * Known OS collisions the owning sprint must settle: ctrl+alt+u (Konsole),
 * ctrl+alt+a (KDE attention), from herdr's avoid list.
 */
export const RESERVED_FOR_LATER = {
  prefixKeys: [
    "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "n", "p", "c", "shift+x", "w", "shift+n", "m", "shift+m",
    "u", "o", "t", "f", "r", "a", "i",
  ],
  chords: [
    "ctrl+alt+1", "ctrl+alt+2", "ctrl+alt+3", "ctrl+alt+4", "ctrl+alt+5",
    "ctrl+alt+6", "ctrl+alt+7", "ctrl+alt+8", "ctrl+alt+9",
    "ctrl+alt+]", "ctrl+alt+[", "ctrl+alt+c", "ctrl+alt+w",
    "ctrl+alt+shift+]", "ctrl+alt+shift+[", "ctrl+alt+m", "ctrl+alt+u",
    "ctrl+alt+o", "ctrl+alt+y", "ctrl+alt+f", "ctrl+alt+r", "ctrl+alt+a",
    "ctrl+alt+i",
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
    // setPrefix is the only writer and runs the full isUsablePrefix check;
    // this read only refuses a hand-edited value that could eat typing.
    const c = saved ? parseCombo(saved) : null;
    if (c && c.key && c.ctrl && !c.mod && !c.meta) return saved!;
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

/** A prefix needs ctrl or alt (a bare or shift-only key would eat typing, a
 *  ⌘ combo would collide with the legacy rows) and must not be a row's chord. */
export function isUsablePrefix(spec: string): boolean {
  const c = parseCombo(spec);
  if (!c.key || c.mod || c.meta) return false;
  if (!c.ctrl && !c.alt) return false;
  if (c.alt && !c.ctrl) return false; // plain alt composes characters on macOS
  const phys = physicalKey(c, "mac");
  return !KEYMAP.some((r) => r.chord && physicalKey(parseCombo(r.chord), "mac") === phys);
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
  opts: { prefix?: string; platforms?: readonly Platform[] } = {},
): KeymapProblem[] {
  const problems: KeymapProblem[] = [];
  const prefix = opts.prefix ?? DEFAULT_PREFIX;
  const handlers = new Set(handlerIds);
  const reservedPrefix = new Set<string>(RESERVED_FOR_LATER.prefixKeys);
  const reservedChord = new Set<string>(RESERVED_FOR_LATER.chords.map(normalizeCombo));

  for (const r of rows) {
    if (!handlers.has(r.action)) {
      problems.push({ kind: "missing-handler", row: r.id, detail: `no handler for "${r.action}"` });
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
