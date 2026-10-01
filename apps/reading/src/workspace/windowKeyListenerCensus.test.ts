import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * One keymap owner: the census of window-level `keydown` listeners.
 *
 * `components/hotkeys/keymap.ts` states the contract in its own header —
 * "Every key the app answers to is a row in KEYMAP; nothing else may define a
 * binding" — while seven production modules register their own window-level
 * `keydown` handler. The contract is documented, not enforced, and the surface
 * has grown: an audit counted three such modules in September 2026 and found
 * six today.
 *
 * This file does not refactor those six. Migrating a modal's Escape, a slash
 * menu's arrows, an editor's capture pass and a float menu's navigation onto
 * one dispatcher is a real design change with real regression risk, and doing
 * it blind would be worse than the drift. What this file does is make the set
 * CLOSED and DECLARED: every listener carries a reason, a seventh one fails
 * here, and a removal fails too, so the list cannot quietly go stale.
 *
 * The debt stays visible in the table below rather than in a comment nobody
 * reads. When a module is migrated onto the dispatcher, delete its row.
 */

const SRC = join(__dirname, "..");

/** Not tests, not stories: only shipped modules count. */
const SKIP = /(\.test\.|\.spec\.|\.stories\.)/;
const REGISTRATION = /window\.addEventListener\(\s*["']keydown["']/g;

/**
 * The declared set. Each entry is a shipped module that registers a window-level
 * keydown listener, with the reason it has not moved onto the dispatcher yet.
 * A module that registers a SECOND listener still needs only one row here; the
 * count per file is asserted separately below.
 */
const DECLARED: Record<string, string> = {
  "workspace/shortcuts.ts":
    "THE dispatcher. Two registrations by design: a capture pass for the prefix and scope arbitration, a bubble pass for chords.",
  "components/CommandPalette.tsx":
    "The palette's own Escape and arrow handling, live only while the palette is open.",
  "components/lemon/LemonModal.tsx":
    "Modal Escape and close, gated on the modal's `open` prop.",
  "modes/Notebook/SlashMenu.tsx":
    "Slash-menu arrow/Enter navigation, live only while the menu is open.",
  "modes/Write/Editor/Editor.tsx":
    "The editor's own CAPTURE pass for writing-mode keys, which must beat the dispatcher while the caret is in the document.",
  "modes/shared/FloatMenu/FloatMenu.tsx":
    "Float-menu navigation, live only while a selection is active.",
  "workspace/PanelLayoutPanel.tsx":
    "Panel-level Escape while the panel holds focus.",
};

/** Every .ts/.tsx under src/, excluding tests and stories. */
function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules") continue;
      sourceFiles(full, out);
    } else if (/\.tsx?$/.test(entry) && !SKIP.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

function census(): { files: string[]; registrations: Map<string, number>; scanned: number } {
  const files: string[] = [];
  const registrations = new Map<string, number>();
  const all = sourceFiles(SRC);
  for (const full of all) {
    const source = readFileSync(full, "utf8");
    const hits = source.match(REGISTRATION);
    if (hits && hits.length > 0) {
      const key = relative(SRC, full);
      files.push(key);
      registrations.set(key, hits.length);
    }
  }
  return { files: files.sort(), registrations, scanned: all.length };
}

describe("window-level keydown listeners: a closed, declared set", () => {
  it("the scan is not vacuous", () => {
    const { scanned, files } = census();
    // A walk that finds nothing would satisfy the equality below trivially.
    expect(scanned).toBeGreaterThan(200);
    expect(files.length).toBeGreaterThan(0);
  });

  it("every module that registers a window keydown listener is declared, with a reason", () => {
    const { files } = census();
    const undeclared = files.filter((f) => !(f in DECLARED));
    expect(undeclared).toEqual([]);
    for (const [file, reason] of Object.entries(DECLARED)) {
      expect(reason.length, `${file} needs a reason`).toBeGreaterThan(20);
    }
  });

  it("no declared module has stopped registering — the declaration cannot go stale", () => {
    const { files } = census();
    const stale = Object.keys(DECLARED).filter((f) => !files.includes(f));
    expect(stale).toEqual([]);
  });

  it("the dispatcher is exactly the module with two registrations", () => {
    const { registrations } = census();
    const doubly = [...registrations.entries()].filter(([, n]) => n > 1).map(([f]) => f);
    expect(doubly).toEqual(["workspace/shortcuts.ts"]);
    expect(registrations.get("workspace/shortcuts.ts")).toBe(2);
  });

  it("the declared set is the size the audit measured — growth is a decision, not a drift", () => {
    const { files } = census();
    // Six modules outside the dispatcher plus the dispatcher itself. A seventh
    // module must be added to DECLARED deliberately, with its reason, in the PR
    // that adds it.
    expect(files).toHaveLength(7);
  });
});
