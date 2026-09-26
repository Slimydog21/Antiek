/**
 * keymap.test.ts — MS-01 milestone 4 + 7: the table-driven integrity guard.
 *
 * validateKeymap is run on the real table (it must find nothing), and on
 * deliberately broken copies (it must find each break). A guard that has
 * never been seen to fail proves nothing, so each negative case below is the
 * guard's own control.
 */
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ACTIONS,
  KEYMAP,
  KEYMAP_DECISION,
  RESERVED_FOR_LATER,
  isUsablePrefix,
  readPrefix,
  setPrefix,
  validateKeymap,
  type ActionId,
  type KeymapRow,
} from "./keymap";
import { comboParts } from "./keymapView";
import { ariaKeyshortcutsFor } from "./bindings";
import { pinPlatform, unpinPlatform } from "../../workspace/keymapTestKit";
import { createActionHandlers } from "../../workspace/shortcuts";

const handlerIds = Object.keys(createActionHandlers((() => {}) as never));

describe("the real keymap is sound", () => {
  it("has no duplicate key, no handler-less action, no uncited D2 row, on either platform", () => {
    expect(validateKeymap(KEYMAP, handlerIds)).toEqual([]);
  });

  it("every action in ACTIONS has a handler, and every handler an action", () => {
    expect([...handlerIds].sort()).toEqual(Object.keys(ACTIONS).sort());
  });

  it("every action the table binds is reachable by at least one key", () => {
    for (const action of Object.keys(ACTIONS) as ActionId[]) {
      expect(KEYMAP.some((r) => r.action === action), action).toBe(true);
    }
  });
});

describe("the guard fails when the table is wrong (negative controls)", () => {
  const row = (over: Partial<KeymapRow>): KeymapRow => ({
    id: "probe",
    action: "palette.toggle",
    scope: "outside-text",
    origin: "legacy-SPR-08",
    ...over,
  });

  it("fails on a duplicate combo", () => {
    const problems = validateKeymap([...KEYMAP, row({ chord: "mod+j" })], handlerIds);
    expect(problems.some((p) => p.kind === "duplicate" && p.row === "probe")).toBe(true);
  });

  it("fails on a duplicate prefix key", () => {
    const problems = validateKeymap(
      [...KEYMAP, row({ prefixKey: "g", origin: "herdr-default", decision: KEYMAP_DECISION })],
      handlerIds,
    );
    expect(problems.some((p) => p.kind === "duplicate" && p.row === "probe")).toBe(true);
  });

  it("fails on a table action with no handler", () => {
    const problems = validateKeymap(
      [...KEYMAP, row({ action: "tab.next" as ActionId, chord: "mod+." })],
      handlerIds,
    );
    expect(problems).toContainEqual(expect.objectContaining({ kind: "missing-handler", row: "probe" }));
  });

  it("fails when the dispatcher drops a handler the table still names", () => {
    const problems = validateKeymap(KEYMAP, handlerIds.filter((h) => h !== "door.read"));
    expect(problems).toContainEqual(expect.objectContaining({ kind: "missing-handler", row: "prod-read" }));
  });

  it("is platform-aware: ⌘B on every platform would collide with the ctrl+b prefix off the Mac", () => {
    const everywhere = KEYMAP.map((r) => (r.id === "projecttree" ? { ...r, platforms: undefined } : r));
    const problems = validateKeymap(everywhere, handlerIds);
    expect(problems).toContainEqual(
      expect.objectContaining({ kind: "duplicate", row: "projecttree", detail: expect.stringContaining("other") }),
    );
  });

  it("fails on a D2 row that does not cite the decision record", () => {
    const problems = validateKeymap([...KEYMAP, row({ chord: "ctrl+alt+g", origin: "D2" })], handlerIds);
    expect(problems).toContainEqual(expect.objectContaining({ kind: "missing-decision", row: "probe" }));
  });

  it("fails on a plain alt chord (macOS composes it into a character)", () => {
    const problems = validateKeymap(
      [...KEYMAP, row({ chord: "alt+g", origin: "D2", decision: KEYMAP_DECISION })],
      handlerIds,
    );
    expect(problems).toContainEqual(expect.objectContaining({ kind: "plain-alt-chord", row: "probe" }));
  });

  it("fails on a key the D2 table reserves for a later sprint", () => {
    const problems = validateKeymap(
      [...KEYMAP, row({ prefixKey: "1", origin: "herdr-default", decision: KEYMAP_DECISION })],
      handlerIds,
    );
    expect(problems).toContainEqual(expect.objectContaining({ kind: "reserved-key", row: "probe" }));
  });

  it("fails on a prefix row that claims to fire inside text", () => {
    const problems = validateKeymap(
      [...KEYMAP, row({ prefixKey: "e", scope: "anywhere", origin: "herdr-default", decision: KEYMAP_DECISION })],
      handlerIds,
    );
    expect(problems).toContainEqual(expect.objectContaining({ kind: "prefix-scope", row: "probe" }));
  });

  it("fails when a different prefix collides with a chord", () => {
    const problems = validateKeymap(KEYMAP, handlerIds, { prefix: "ctrl+alt+b" });
    expect(problems.some((p) => p.kind === "duplicate")).toBe(true);
    expect(isUsablePrefix("ctrl+alt+b")).toBe(false);
    expect(isUsablePrefix("ctrl+a")).toBe(true);
    expect(isUsablePrefix("ctrl+b")).toBe(true); // the default
    expect(isUsablePrefix("b")).toBe(false);
    expect(isUsablePrefix("alt+b")).toBe(false);
    expect(isUsablePrefix("mod+b")).toBe(false);
  });

  it("refuses a prefix that is a row's key on the other platform (critic r1 #3)", () => {
    // Off the Mac, "mod" is Ctrl: ctrl+k is ⌘K's key and ctrl+j is ⌘J's.
    expect(isUsablePrefix("ctrl+k")).toBe(false);
    expect(isUsablePrefix("ctrl+j")).toBe(false);
    expect(isUsablePrefix("ctrl+shift+p")).toBe(false);
    expect(validateKeymap(KEYMAP, handlerIds, { prefix: "ctrl+k" }).some((p) => p.kind === "duplicate")).toBe(true);
  });
});

describe("every SPR-08 binding moved into the table (M4 migration list)", () => {
  it.each([
    ["mod+k", "palette.toggle"],
    ["mod+shift+p", "palette.toggle"],
    ["mod+j", "door.research"],
    ["mod+e", "door.read"],
    ["mod+y", "door.write"],
    ["mod+u", "door.speak"],
    ["mod+o", "door.home"],
    ["mod+i", "door.more"],
    ["mod+[", "panel.focusPrev"],
    ["mod+]", "panel.focusNext"],
    ["mod+w", "panel.closeFloating"],
    ["mod+b", "projecttree.toggle"],
    ["mod+/", "aisidecar.toggle"],
    ["mod+g", "door.researchHome"],
    ["mod+;", "door.readLibrary"],
    ["?", "keysheet.toggle"],
  ])("%s is a legacy-SPR-08 row for %s", (chord, action) => {
    const hit = KEYMAP.find((r) => r.chord === chord);
    expect(hit?.action).toBe(action);
    expect(hit?.origin).toBe("legacy-SPR-08");
  });
});

describe("the cockpit pane rows (C3) and companion rows (C4): bound, twinned, and out of RESERVED_FOR_LATER", () => {
  it.each([
    ["prefix-pane-left", "pane.focusLeft", "h", "ctrl+alt+h"],
    ["prefix-pane-right", "pane.focusRight", "l", "ctrl+alt+l"],
    ["prefix-pane-full", "pane.fullscreen", "f", "ctrl+alt+f"],
    ["prefix-layout-preset", "layout.togglePreset", "i", "ctrl+alt+i"],
    ["prefix-agent-next", "companion.nextTab", "n", "ctrl+alt+]"],
    ["prefix-agent-prev", "companion.prevTab", "p", "ctrl+alt+["],
  ])("%s binds %s as prefix+%s with the %s twin", (id, action, prefixKey, chord) => {
    const prefixRow = KEYMAP.find((r) => r.id === id);
    expect(prefixRow?.action).toBe(action);
    expect(prefixRow?.prefixKey).toBe(prefixKey);
    expect(prefixRow?.scope).toBe("outside-text");
    expect(prefixRow?.origin).toBe("D2");
    expect(prefixRow?.decision).toContain("mothership-keys-herdr-prefix.md");
    const chordRow = KEYMAP.find((r) => r.action === action && r.chord === chord);
    expect(chordRow, `the chord twin ${chord}`).toBeTruthy();
    expect(chordRow?.origin).toBe("D2");
  });

  it("no reserved row is left behind for the keys the cockpit rows took", () => {
    // h and l were never reserved; f, i, n, p (prefix) and the six chords
    // were, and must be gone now that the rows own them.
    for (const k of ["h", "l", "f", "i", "n", "p"]) {
      expect(RESERVED_FOR_LATER.prefixKeys).not.toContain(k);
    }
    for (const c of ["ctrl+alt+h", "ctrl+alt+l", "ctrl+alt+f", "ctrl+alt+i", "ctrl+alt+]", "ctrl+alt+["]) {
      expect(RESERVED_FOR_LATER.chords).not.toContain(c);
    }
    // And every remaining reserved key is still refused to a probing row.
    const probe = validateKeymap(
      [...KEYMAP, { id: "probe", action: "palette.toggle", prefixKey: "1", scope: "outside-text", origin: "D2", decision: KEYMAP_DECISION }],
      handlerIds,
    );
    expect(probe).toContainEqual(expect.objectContaining({ kind: "reserved-key", row: "probe" }));
  });
});

describe("D2 rows cite the decision record, and the record exists (M7)", () => {  it("every D2 and herdr-default row carries the record's path", () => {
    const cited = KEYMAP.filter((r) => r.origin === "D2" || r.origin === "herdr-default");
    expect(cited.length).toBeGreaterThan(0);
    for (const r of cited) {
      expect(r.decision, r.id).toContain("docs/decisions/mothership-keys-herdr-prefix.md");
      expect(r.decision, r.id).toContain("DECISIONS.md D2");
    }
  });

  it("the record is in the repository and records the rejected options", () => {
    const path = resolve(import.meta.dirname, "../../../../../docs/decisions/mothership-keys-herdr-prefix.md");
    expect(existsSync(path)).toBe(true);
    const text = readFileSync(path, "utf8");
    expect(text).toMatch(/SPR-08/);
    expect(text).toMatch(/option|composition/i);
    expect(text).toMatch(/Reconsider|reverse/i);
  });
});

describe("rendering helpers read the same table", () => {
  it("aria-keyshortcuts lists every direct key of an action, never a prefix sequence", () => {
    try {
      pinPlatform("mac");
      expect(ariaKeyshortcutsFor("palette.toggle")).toBe("Meta+K Meta+Shift+P");
      expect(ariaKeyshortcutsFor("projecttree.toggle")).toBe("Meta+B Control+Alt+B");
      pinPlatform("other");
      expect(ariaKeyshortcutsFor("palette.toggle")).toBe("Control+K Control+Shift+P");
      // Off the Mac ⌘B is not a row (ctrl+b is the prefix): only the chord.
      expect(ariaKeyshortcutsFor("projecttree.toggle")).toBe("Control+Alt+B");
      expect(ariaKeyshortcutsFor("keysheet.toggle")).toBe("?");
    } finally {
      unpinPlatform();
    }
  });

  it("comboParts renders one keycap per key", () => {
    expect(comboParts("ctrl+alt+b", "mac")).toEqual(["⌃", "⌥", "B"]);
    expect(comboParts("ctrl+alt+b", "other")).toEqual(["Ctrl", "Alt", "B"]);
    expect(comboParts("mod+shift+p", "mac")).toEqual(["⌘", "⇧", "P"]);
  });
});

describe("the prefix is configurable, never onto a taken key", () => {
  it("setPrefix saves a free combo, refuses a taken one, and null restores ctrl+b", () => {
    try {
      expect(setPrefix("ctrl+k")).toBe(false);
      expect(readPrefix()).toBe("ctrl+b");
      expect(setPrefix("Ctrl+A")).toBe(true);
      expect(readPrefix()).toBe("ctrl+a");
      // A hand-edited value that is not a ctrl combo is ignored.
      for (const bad of ["b", "meta+b", "mod+b", "alt+b", "shift+b"]) {
        window.localStorage.setItem("antiek.keymap.prefix", bad);
        expect(readPrefix(), bad).toBe("ctrl+b");
      }
      expect(setPrefix(null)).toBe(true);
      expect(readPrefix()).toBe("ctrl+b");
    } finally {
      window.localStorage.removeItem("antiek.keymap.prefix");
    }
  });

  it("a stored prefix that now collides with a key is ignored on read, not trusted (carrier critic r1)", () => {
    try {
      // ctrl+alt+b is the sidebar chord; ctrl+k is ⌘K off the Mac. Both are
      // well-formed ctrl combos, so only the full check refuses them.
      for (const taken of ["ctrl+alt+b", "ctrl+k"]) {
        window.localStorage.setItem("antiek.keymap.prefix", taken);
        expect(readPrefix(), taken).toBe("ctrl+b");
      }
      window.localStorage.setItem("antiek.keymap.prefix", "ctrl+a");
      expect(readPrefix()).toBe("ctrl+a");
    } finally {
      window.localStorage.removeItem("antiek.keymap.prefix");
    }
  });
});
