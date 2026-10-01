import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Global keyboard handlers: a closed, declared, mechanically-checked set.
 *
 * `components/hotkeys/keymap.ts` says "Every key the app answers to is a row in
 * KEYMAP; nothing else may define a binding." In practice many modules attach
 * their own listener to `window`, `globalThis` or `document` for a keyboard
 * event. This file does not migrate them — moving a dropdown's Escape, a
 * fullscreen exit, a menu's arrows and an editor's undo detector onto one
 * dispatcher is a design change with real regression risk. It makes the set
 * closed and declared, so growth is a decision rather than drift.
 *
 * ── THE COUNT GREW EVERY TIME THE SCAN GOT HONEST ──────────────────────────
 * A September 2026 audit matched the literal `window.addEventListener("keydown"`
 * and reported THREE modules. The review built on it said SEVEN. A critic then
 * defeated the seven-row gate by planting four spellings it missed — a template
 * literal, a const event name, `globalThis`, and `onkeydown =` — and, having
 * planted them, showed the seven rows were also partly FALSE.
 *
 * This scan reads any `addEventListener` on a global receiver whose event name
 * mentions a key, stripping TypeScript assertions first (`"x" as keyof Y` is a
 * type, not an event — a naive /key/ test counts `keyof` and inflates the set).
 * With that rule the real extent is EIGHTEEN files and nineteen registrations,
 * not seven. The earlier numbers were artefacts of a weak matcher.
 *
 * ── ASSERTED vs COMMENTARY ────────────────────────────────────────────────
 * Only mechanically-derivable facts are asserted: which files, how many
 * registrations each, and whether any registration is capture-phase. An earlier
 * revision asserted a prose "reason" per module and only checked it was longer
 * than 20 characters; a critic read the handlers and found four of seven false
 * (the palette was said to handle arrows — it handles Escape; the editor was
 * said to "beat the dispatcher" — it only sets a flag on Cmd/Ctrl+Z). Prose a
 * test cannot verify will rot, so the commentary below is labelled and not
 * asserted.
 */

const SRC = join(__dirname, "..");
const SKIP = /(\.test\.|\.spec\.|\.stories\.)/;
const SOURCE_EXT = /\.(ts|tsx|js|jsx|mjs)$/;

/** A registration on a global receiver, first argument captured. */
const GLOBAL_ADD = /(window|globalThis|document)\s*\.\s*addEventListener\(\s*([^;]{0,200}?)\)/g;
/** A global assignment spelling that installs a handler without addEventListener. */
const GLOBAL_ONKEYDOWN = /(window|globalThis|document)\s*\.\s*onkey\w+\s*=/g;

interface Row {
  registrations: number;
  capture: boolean;
}

/**
 * The declared set: every module with a global keyboard registration, the number
 * it installs, and whether it is capture-phase. Counted on origin/main.
 */
const DECLARED: Record<string, Row> = {
  "components/CommandPalette.tsx": { registrations: 1, capture: false },
  "components/ModelPicker.tsx": { registrations: 1, capture: false },
  "components/lemon/LemonDropdown.tsx": { registrations: 1, capture: false },
  "components/lemon/LemonModal.tsx": { registrations: 1, capture: false },
  "components/lemon/LemonSelect.tsx": { registrations: 1, capture: false },
  "modes/Notebook/SlashMenu.tsx": { registrations: 1, capture: false },
  "modes/Reading/index.tsx": { registrations: 1, capture: false },
  "modes/Reading/island/ThreadIsland.tsx": { registrations: 1, capture: false },
  "modes/Write/Editor/Editor.tsx": { registrations: 1, capture: true },
  "modes/Write/WriteHome.tsx": { registrations: 1, capture: false },
  "modes/shared/FloatMenu/FloatMenu.tsx": { registrations: 1, capture: false },
  "workspace/CompanionPane.tsx": { registrations: 1, capture: false },
  "workspace/DocumentTabStrip.tsx": { registrations: 1, capture: false },
  "workspace/PanelLayout.tsx": { registrations: 1, capture: false },
  "workspace/PanelLayoutPanel.tsx": { registrations: 1, capture: false },
  "workspace/TabPathHeader.tsx": { registrations: 1, capture: false },
  "workspace/WriteOutlinePane.tsx": { registrations: 1, capture: false },
  // THE dispatcher: a capture pass for the prefix and scope arbitration, a
  // bubble pass for chords. The only module that should own global keys.
  "workspace/shortcuts.ts": { registrations: 2, capture: true },
};

/**
 * COMMENTARY, NOT ASSERTED — read from the handlers, and corrected after a
 * critic showed the previous version of this list was wrong on four rows.
 *
 *   shortcuts.ts          the dispatcher (2 registrations: capture + bubble)
 *   CommandPalette.tsx    Escape only, while `open`
 *   ModelPicker.tsx       Escape only, while `open` (document-level)
 *   LemonDropdown.tsx     Escape/dismiss while open
 *   LemonModal.tsx        Escape only, gated on `open && !forceUserAction`
 *                         and on topModal() being this dialog
 *   LemonSelect.tsx       Escape/dismiss while open
 *   SlashMenu.tsx         ArrowDown/ArrowUp/Enter/Escape; no internal open gate
 *   Reading/index.tsx     reader-level keyboard handling
 *   ThreadIsland.tsx      island-level keyboard handling
 *   Editor.tsx            capture-phase and PASSIVE: sets nextUpdateIsRevert on
 *                         Cmd/Ctrl+Z so the next onUpdate is flagged reverted.
 *                         It prevents nothing.
 *   WriteHome.tsx         screen-level keyboard handling
 *   FloatMenu.tsx         Escape only, gated on `selection`, yields to topModal()
 *   CompanionPane.tsx     Escape for the overflow menu, yields to topModal()
 *   DocumentTabStrip.tsx  tab-strip keyboard handling
 *   PanelLayout.tsx       Escape to leave fullscreen, guarded by escOverlayOpen()
 *   PanelLayoutPanel.tsx  Escape only, gated on a floating focused panel; skips
 *                         text inputs and contenteditable
 *   TabPathHeader.tsx     header keyboard handling
 *   WriteOutlinePane.tsx  outline-pane keyboard handling
 */

/** Event names in the first argument, with TypeScript assertions removed. */
function eventNames(argText: string): string[] {
  const head = argText.split(/\s+as\s+/)[0].trim();
  const quoted = [...head.matchAll(/[`'"]([^`'"]+)[`'"]/g)].map((m) => m[1]);
  if (quoted.length > 0) return quoted;
  const ident = /^([A-Za-z_$][\w$]*)/.exec(head);
  return ident ? [ident[1]] : [];
}

/** Every global keyboard registration in a source string. */
function registrationsIn(source: string): number {
  let n = 0;
  for (const m of source.matchAll(GLOBAL_ADD)) {
    if (eventNames(m[2]).some((e) => /key/i.test(e))) n += 1;
  }
  n += [...source.matchAll(GLOBAL_ONKEYDOWN)].length;
  return n;
}

function isCapture(source: string): boolean {
  for (const m of source.matchAll(GLOBAL_ADD)) {
    if (!eventNames(m[2]).some((e) => /key/i.test(e))) continue;
    if (/,\s*true\s*$/.test(m[2].trim())) return true;
  }
  return false;
}

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules") continue;
      sourceFiles(full, out);
    } else if (SOURCE_EXT.test(entry) && !SKIP.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

function census() {
  const rows = new Map<string, Row>();
  const all = sourceFiles(SRC);
  for (const full of all) {
    const source = readFileSync(full, "utf8");
    const registrations = registrationsIn(source);
    if (registrations > 0) {
      rows.set(relative(SRC, full), { registrations, capture: isCapture(source) });
    }
  }
  return { rows, scanned: all.length };
}

describe("global keyboard handlers: a closed, declared, checked set", () => {
  it("the scan is not vacuous and walks essentially the whole tree", () => {
    const { scanned, rows } = census();
    // A first revision asserted >200 against a 553-file tree (36%), which a walk
    // that silently loses a subtree would still satisfy. Measured, then set.
    expect(scanned).toBeGreaterThan(500);
    expect(rows.size).toBeGreaterThan(0);
    expect(rows.has("workspace/shortcuts.ts")).toBe(true);
  });

  it("the matcher catches every spelling a critic planted, and ignores types", () => {
    const planted = [
      'window.addEventListener("keydown", h);',
      "globalThis.addEventListener(`key${suffix}`, h);",
      "document.addEventListener(KEYDOWN_EVENT, h);",
      "window.onkeydown = h;",
    ];
    for (const line of planted) {
      expect(registrationsIn(line), `missed: ${line}`).toBeGreaterThan(0);
    }
    // Non-key listeners are not counted...
    expect(registrationsIn('window.addEventListener("resize", h);')).toBe(0);
    // ...and a TypeScript assertion is not an event name. `keyof` is the trap
    // that made an earlier revision of this scan over-count.
    expect(registrationsIn('window.addEventListener("antiek:palette:toggle" as keyof WindowEventMap, h);')).toBe(0);
    // An element-level handler is not a global binding.
    expect(registrationsIn("el.onkeydown = h;")).toBe(0);
  });

  it("exactly the declared modules register a global keyboard handler", () => {
    const { rows } = census();
    expect([...rows.keys()].sort()).toEqual(Object.keys(DECLARED).sort());
  });

  it("each module registers the declared number of times, and the declared phase", () => {
    const { rows } = census();
    for (const [file, expected] of Object.entries(DECLARED)) {
      expect(rows.get(file), `${file} missing`).toEqual(expected);
    }
  });

  it("the set is the size this scan measures — growth is a decision, not a drift", () => {
    const { rows } = census();
    // 18 files, 19 registrations. A nineteenth file must be declared in the PR
    // that adds it, with its count and phase.
    expect(rows.size).toBe(18);
    const total = [...rows.values()].reduce((a, r) => a + r.registrations, 0);
    expect(total).toBe(19);
  });
});
