import { describe, expect, it } from "vitest";

import { NOTES } from "./keymapView";
import { readLayoutPreset } from "../../workspace/persistence";

/**
 * The key sheet must not lie about the layout.
 *
 * The shipped copy for `layout.togglePreset` read "The cockpit's two tall panes
 * are the default; docked puts the panels back at the edges", and `keymap.ts`'s
 * comment repeated it. The code disagrees: `readLayoutPreset()` returns
 * "docked" on a miss, a parse error, a schema-version mismatch or an unknown
 * value, and its own comment says why — "a stored preset never surprises an
 * operator who never chose one". So a workspace that has never chosen a preset
 * starts DOCKED, and the sheet told the operator the opposite.
 *
 * This file is the gate for that class: a help string that contradicts the
 * behaviour it documents. It asserts the copy against the reader's real default
 * rather than against a hardcoded sentence, so changing the default legitimately
 * requires changing the copy too.
 */

describe("key-sheet copy agrees with the layout default", () => {
  it("the code's default preset is the one the copy must describe", () => {
    // Pinned deliberately: if someone changes the default to the inset, this
    // line fails and points at the copy that must change with it.
    expect(readLayoutPreset()).toBe("docked");
  });

  it("the toggle is described as summoning the cockpit, not as already being it", () => {
    const help = NOTES["layout.togglePreset"];
    expect(help).toBeTruthy();
    expect(help).not.toMatch(/are the default/i);
    expect(help).not.toMatch(/is the default/i);
    expect(help).toMatch(/docked/i);
  });

  it("the copy names both presets, so the toggle is intelligible without the code", () => {
    const help = NOTES["layout.togglePreset"] ?? "";
    expect(help).toMatch(/inset/i);
    expect(help).toMatch(/cockpit/i);
  });

  it("the default the copy describes is the default a fresh workspace gets", () => {
    // A fresh workspace: no stored preset. The reader is the single source.
    window.localStorage.clear();
    const fresh = readLayoutPreset();
    expect(fresh).toBe("docked");
    const help = NOTES["layout.togglePreset"] ?? "";
    // The copy must not claim the fresh state is the inset.
    expect(help.toLowerCase().indexOf("never chosen")).toBeGreaterThan(-1);
  });
});
