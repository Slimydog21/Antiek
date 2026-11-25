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
  it("every production row explicitly declares its status", () => {
    for (const row of KEYMAP) expect(row.status, `${row.id}/${row.action}: missing status declaration`).toMatch(/^(implemented|unimplemented)$/);
  });

  it("has no duplicate key, no handler-less action, no uncited D2 row, on either platform", () => {
    expect(validateKeymap(KEYMAP, handlerIds)).toEqual([]);
  });

  it("exactly the implemented actions have handlers", () => {
    expect([...handlerIds].sort()).toEqual([...new Set(KEYMAP.filter((r) => r.status !== "unimplemented").map((r) => r.action))].sort());
  });

  it("every action the table binds is reachable by at least one key", () => {
    for (const action of Object.keys(ACTIONS) as ActionId[]) {
      expect(KEYMAP.some((r) => r.action === action), action).toBe(true);
    }
  });
});

describe("the guard fails when the table is wrong (negative controls)", () => {
  const row = (over: Partial<Omit<KeymapRow, "status" | "blockedBy">>): KeymapRow => ({
    id: "probe",
    action: "palette.toggle",
    scope: "outside-text",
    origin: "legacy-SPR-08",
    ...over,
  });


  it("rejects a handler behind an unimplemented declaration and mismatched alias status", () => {
    const pending: KeymapRow = { id: "declared-gap", action: "palette.toggle", chord: "ctrl+alt+z", scope: "anywhere", origin: "legacy-SPR-08", status: "unimplemented", blockedBy: "named authority acceptance" };
    expect(validateKeymap([pending], handlerIds)).toContainEqual(expect.objectContaining({ kind: "unexpected-handler", row: "declared-gap", detail: expect.stringContaining("palette.toggle") }));
    expect(validateKeymap([...KEYMAP, pending], handlerIds)).toContainEqual(expect.objectContaining({ kind: "inconsistent-status", row: "declared-gap" }));
    expect(validateKeymap([pending], handlerIds.filter((id) => id !== "palette.toggle"))).toEqual([]);
  });

  it("names a missing scenario, unpressed alias, and removed sheet row", () => {
    const action = "palette.toggle";
    const rows = KEYMAP.filter((r) => r.action === action);
    const ids = rows.map((r) => r.id);
    const problems = validateKeymap(rows, handlerIds, { coverage: { scenarios: [], exercisedRows: ids.slice(1), sheetRows: ids.slice(1) } });
    expect(problems).toContainEqual(expect.objectContaining({ kind: "missing-scenario", row: ids[0], detail: expect.stringContaining(action) }));
    expect(problems).toContainEqual(expect.objectContaining({ kind: "unexercised-row", row: ids[0] }));
    expect(problems).toContainEqual(expect.objectContaining({ kind: "missing-sheet-row", row: ids[0] }));
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
      [...KEYMAP, row({ action: "tab.nonexistent" as ActionId, chord: "mod+." })],
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

describe("the cockpit pane rows (C3) and tab rows (D6, lane-A cockpit decision): bound, twinned, and out of RESERVED_FOR_LATER", () => {
  it.each([
    ["prefix-pane-left", "pane.focusLeft", "h", "ctrl+alt+h"],
    ["prefix-pane-right", "pane.focusRight", "l", "ctrl+alt+l"],
    ["prefix-pane-full", "pane.fullscreen", "f", "ctrl+alt+f"],
    // n/p + ctrl+alt+]/[ act on the FOCUSED pane's tabs (one pair, no ,/.).
    ["prefix-tab-next", "tab.next", "n", "ctrl+alt+]"],
    ["prefix-tab-prev", "tab.prev", "p", "ctrl+alt+["],
    ["prefix-tab-new", "tab.new", "c", "ctrl+alt+c"],
    ["prefix-tab-parent", "tab.parent", "u", "ctrl+alt+u"],
    ["prefix-tab-child", "tab.visitChild", "o", "ctrl+alt+o"],
    ["prefix-tab-tree", "tab.treeToggle", "t", "ctrl+alt+y"],
    ["prefix-inbox", "inbox.toggle", "i", "ctrl+alt+i"],
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

  it("tab.close is prefix+shift+x with NO chord twin (destructive acts stay behind the prefix)", () => {
    const row = KEYMAP.find((r) => r.id === "prefix-tab-close");
    expect(row?.action).toBe("tab.close");
    expect(row?.prefixKey).toBe("shift+x");
    expect(row?.scope).toBe("outside-text");
    expect(KEYMAP.some((r) => r.action === "tab.close" && r.chord)).toBe(false);
  });

  it("layout.togglePreset is prefix+shift+i with NO chord twin (i is the inbox's)", () => {
    const rows = KEYMAP.filter((r) => r.action === "layout.togglePreset");
    expect(rows).toHaveLength(1);
    expect(rows[0].prefixKey).toBe("shift+i");
    expect(rows[0].chord).toBeUndefined();
  });

  it("no reserved row is left behind for the keys the cockpit rows took", () => {
    // h and l and , and . were never reserved; the rest were, and must be
    // gone now that the rows own them.
    for (const k of ["h", "l", "f", "i", "n", "p", "u", "o", "c", "t", "shift+x"]) {
      expect(RESERVED_FOR_LATER.prefixKeys).not.toContain(k);
    }
    for (const c of [
      "ctrl+alt+h", "ctrl+alt+l", "ctrl+alt+f", "ctrl+alt+i",
      "ctrl+alt+]", "ctrl+alt+[", "ctrl+alt+u", "ctrl+alt+o", "ctrl+alt+c", "ctrl+alt+y",
    ]) {
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

// ─── SPR-07 (agent pane): prefix+a / ctrl+alt+a taken under D2 (invariant 33) ───

describe("the agent pane rows (SPR-07): one action, two aliases, one status, out of RESERVED_FOR_LATER", () => {
  const prefixRow = KEYMAP.find((r) => r.id === "prefix-agent-pane");
  const chordRow = KEYMAP.find((r) => r.id === "chord-agent-pane");

  it("binds agent.openPane as prefix+a with the ctrl+alt+a twin", () => {
    expect(prefixRow?.action).toBe("agent.openPane");
    expect(prefixRow?.prefixKey).toBe("a");
    expect(prefixRow?.scope).toBe("outside-text");
    expect(chordRow?.action).toBe("agent.openPane");
    expect(chordRow?.chord).toBe("ctrl+alt+a");
    expect(chordRow?.scope).toBe("anywhere");
    expect(prefixRow?.origin).toBe("D2");
    expect(prefixRow?.decision).toContain("mothership-keys-herdr-prefix.md");
  });

  it("both rows share one status; while unimplemented the blocker names F1 and no handler exists", () => {
    expect(prefixRow?.status).toBe(chordRow?.status);
    expect(validateKeymap(KEYMAP, handlerIds)).toEqual([]);
    if (prefixRow?.status === "unimplemented") {
      expect(prefixRow.blockedBy).toContain("F1");
      expect(handlerIds).not.toContain("agent.openPane");
    } else {
      expect(handlerIds).toContain("agent.openPane");
    }
  });

  it("a and ctrl+alt+a left RESERVED_FOR_LATER; the remaining reserved keys still refuse a probe", () => {
    expect(RESERVED_FOR_LATER.prefixKeys).not.toContain("a");
    expect(RESERVED_FOR_LATER.chords).not.toContain("ctrl+alt+a");
    const probe = validateKeymap(
      [...KEYMAP, { id: "probe", action: "palette.toggle", prefixKey: "w", scope: "outside-text", origin: "D2", decision: KEYMAP_DECISION }],
      handlerIds,
    );
    expect(probe).toContainEqual(expect.objectContaining({ kind: "reserved-key", row: "probe" }));
  });
});
describe("SPR-10 agent rows (lane-A-proposed, pending ratification): shift+j (jump to the toast's agent) and shift+g (the shifted Switcher key)", () => {
  it.each([
    ["prefix-agents-toast", "agents.gotoToast", "shift+j", "ctrl+alt+shift+j"],
    ["prefix-agents-goto", "agents.goto", "shift+g", "ctrl+alt+g"],
  ])("%s binds %s as prefix+%s with the %s chord twin", (id, action, prefixKey, chord) => {
    const prefixRow = KEYMAP.find((r) => r.id === id);
    expect(prefixRow?.action).toBe(action);
    expect(prefixRow?.prefixKey).toBe(prefixKey);
    expect(prefixRow?.scope).toBe("outside-text");
    expect(prefixRow?.origin).toBe("lane-A-proposed");
    expect(prefixRow?.decision).toMatch(/SPR-10 agent monitoring 2026-10-07T23:06Z/);
    const chordRow = KEYMAP.find((r) => r.action === action && r.chord === chord);
    expect(chordRow?.scope).toBe("anywhere");
    expect(chordRow?.origin).toBe("lane-A-proposed");
  });

  it("negative controls: the literal herdr keys o and g are duplicates here, and so are PR 3751's shift+o and ctrl+alt+shift+o (on main); a and ctrl+alt+a are the agent pane's (SPR-07, on main)", () => {
    const probe = (over: Partial<KeymapRow>): KeymapRow => ({ id: "probe", action: "agents.gotoToast", scope: "outside-text", origin: "lane-A-proposed", decision: "probe", ...over } as KeymapRow);
    expect(validateKeymap([...KEYMAP, probe({ prefixKey: "o" })], handlerIds)).toContainEqual(expect.objectContaining({ kind: "duplicate", row: "probe", detail: expect.stringContaining("prefix-tab-child") }));
    // The sprint's first binding (shift+o / ctrl+alt+shift+o) is #3751's switcher.open, on main since 497a2ce05; it is a duplicate of KEYMAP itself.
    expect(validateKeymap([...KEYMAP, probe({ prefixKey: "shift+o" })], handlerIds)).toContainEqual(expect.objectContaining({ kind: "duplicate", row: "probe", detail: expect.stringContaining("prefix-switcher-open") }));
    expect(validateKeymap([...KEYMAP, probe({ chord: "ctrl+alt+shift+o", scope: "anywhere" })], handlerIds)).toContainEqual(expect.objectContaining({ kind: "duplicate", row: "probe", detail: expect.stringContaining("chord-switcher-open") }));
    expect(validateKeymap([...KEYMAP, probe({ action: "agents.goto", prefixKey: "g" })], handlerIds)).toContainEqual(expect.objectContaining({ kind: "duplicate", row: "probe", detail: expect.stringContaining("prefix-goto") }));
    // a / ctrl+alt+a were island.open's reserve when this test was written;
    // SPR-07 (#3756) took them for the agent pane, so the probe now reads as
    // a duplicate of the real rows, not reserved-key.
    expect(validateKeymap([...KEYMAP, probe({ prefixKey: "a" })], handlerIds)).toContainEqual(expect.objectContaining({ kind: "duplicate", row: "probe", detail: expect.stringContaining("prefix-agent-pane") }));
    expect(validateKeymap([...KEYMAP, probe({ chord: "ctrl+alt+a", scope: "anywhere" })], handlerIds)).toContainEqual(expect.objectContaining({ kind: "duplicate", row: "probe", detail: expect.stringContaining("chord-agent-pane") }));
    // ctrl+alt+shift+j carries shift in the physical-key check, so a later plain ctrl+alt+j stays free.
    expect(validateKeymap(KEYMAP, handlerIds)).toEqual([]);
    expect(RESERVED_FOR_LATER.prefixKeys).not.toContain("a");
    expect(RESERVED_FOR_LATER.chords).not.toContain("ctrl+alt+a");
  });

  it("no collision with the open lanes' rows NOT yet on main: PR 3754's pane-flow rows (flag on) beside KEYMAP leave no duplicate prefix key or chord on either platform", () => {
    // PR 3751's switcher.open rows are on main (497a2ce05), so KEYMAP itself
    // carries them and they are not appended here; this pins that premise.
    expect(KEYMAP.filter((r) => r.action === "switcher.open").map((r) => r.prefixKey ?? r.chord)).toEqual(["shift+o", "ctrl+alt+shift+o"]);
    // PR 3756's agent.openPane rows are on main too (merged 2026-10-08), so
    // KEYMAP carries them as well; same premise pin.
    expect(KEYMAP.filter((r) => r.action === "agent.openPane").map((r) => r.prefixKey ?? r.chord)).toEqual(["a", "ctrl+alt+a"]);
    const D = "probe";
    const row = (id: string, action: string, key: { prefixKey: string } | { chord: string }, scope: KeymapRow["scope"] = "outside-text"): KeymapRow =>
      ({ id, action: action as ActionId, status: "implemented", scope, origin: "lane-A-proposed", decision: D, ...key }) as KeymapRow;
    // PR 3754 (origin/sweep/paneflow-land-spr01-20261008 @ 7f6b0569d) with
    // antiek.flag.pane.flow on: ctrl+alt+l leaves pane.focusRight for
    // layout.togglePreset, focus gains the arrows, reorder takes shift+arrow.
    const paneFlowReplaced = new Set(["chord-pane-right"]);
    const paneFlow: KeymapRow[] = [
      row("chord-pane-right", "pane.focusRight", { chord: "ctrl+alt+arrowright" }),
      row("chord-pane-left-arrow", "pane.focusLeft", { chord: "ctrl+alt+arrowleft" }),
      row("prefix-pane-left-arrow", "pane.focusLeft", { prefixKey: "arrowleft" }),
      row("prefix-pane-right-arrow", "pane.focusRight", { prefixKey: "arrowright" }),
      row("chord-pane-reorder-left", "pane.reorderLeft", { chord: "ctrl+alt+shift+arrowleft" }),
      row("chord-pane-reorder-right", "pane.reorderRight", { chord: "ctrl+alt+shift+arrowright" }),
      row("prefix-pane-reorder-left", "pane.reorderLeft", { prefixKey: "shift+arrowleft" }),
      row("prefix-pane-reorder-right", "pane.reorderRight", { prefixKey: "shift+arrowright" }),
      row("chord-layout-preset", "layout.togglePreset", { chord: "ctrl+alt+l" }),
    ];
    // PR 3756's agent.openPane rows are on main, so they live in KEYMAP and
    // are NOT appended. PR 3754's pane-flow rows are sequencing-dependent:
    // this branch can merge before or after #3754 (the wave's union proof
    // caught the simulation double-appending rows KEYMAP already carried),
    // so gate the simulated append on their actual absence — the same
    // premise-pin pattern as the 3751/3756 pins above.
    const ids = [...handlerIds, "pane.reorderLeft", "pane.reorderRight"];
    const duplicates = (rows: readonly KeymapRow[]) => validateKeymap(rows, ids).filter((f) => f.kind === "duplicate");
    if (KEYMAP.some((r) => r.id === "prefix-pane-reorder-left")) {
      // #3754 HAS landed: KEYMAP carries the real rows. Pin against them
      // instead of simulating — the real table validates with no duplicates.
      // (The flag-on block's chord-layout-preset is gated out of KEYMAP in the
      // test env — antiek.flag.pane.flow is off — so the pin is the reorder
      // prefix keys, visible in both flag states.)
      expect(duplicates(KEYMAP)).toEqual([]);
      expect(new Set(KEYMAP.filter((r) => r.id === "prefix-pane-reorder-left").map((r) => r.prefixKey))).toEqual(new Set(["shift+arrowleft"]));
      expect(new Set(KEYMAP.filter((r) => r.id === "prefix-pane-reorder-right").map((r) => r.prefixKey))).toEqual(new Set(["shift+arrowright"]));
      return;
    }
    expect(duplicates([...KEYMAP.filter((r) => !paneFlowReplaced.has(r.id)), ...paneFlow])).toEqual([]);
    // Control: the check is not vacuous. Without PR 3754's replacement,
    // ctrl+alt+l is main's pane.focusRight chord and the layout chord collides.
    expect(duplicates([...KEYMAP, ...paneFlow.filter((r) => !paneFlowReplaced.has(r.id))])).toContainEqual(expect.objectContaining({ kind: "duplicate", row: "chord-layout-preset" }));
  });

  it("the base rows prefix-tab-child, chord-tab-child and prefix-goto are byte-identical to the SPR-06 base", () => {
    const src = readFileSync(resolve(import.meta.dirname, "keymap.ts"), "utf8");
    for (const line of [
      '  { id: "prefix-goto", action: "palette.toggle", status: "implemented", prefixKey: "g", scope: "outside-text", origin: "herdr-default", decision: D },',
      '  { id: "prefix-tab-child", action: "tab.visitChild", status: "implemented", prefixKey: "o", scope: "outside-text", origin: "D2", decision: D },',
      '  { id: "chord-tab-child", action: "tab.visitChild", status: "implemented", chord: "ctrl+alt+o", scope: "anywhere", origin: "D2", decision: D },',
    ]) {
      expect(src.split("\n")).toContain(line);
    }
  });
});
