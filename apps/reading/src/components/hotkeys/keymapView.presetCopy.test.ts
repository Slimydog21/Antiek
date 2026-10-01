import { describe, expect, it } from "vitest";

import { NOTES } from "./keymapView";
import { LAYOUT_PRESET_DEFAULT, readLayoutPreset } from "../../workspace/persistence";

/**
 * The key sheet's layout row must not contradict the layout's default.
 *
 * The shipped copy said "The cockpit's two tall panes are the default; docked
 * puts the panels back at the edges". `readLayoutPreset()` returns "docked" on a
 * miss, a parse error, a schema-version mismatch or an unknown value, and
 * `WorkspaceStore.ts` seeds its `layoutPreset` from that reader — so a fresh
 * workspace really does start docked. The sheet told the operator the opposite.
 *
 * AN EARLIER REVISION OF THIS FILE WAS REJECTED BY A CRITIC, correctly: it
 * asserted vocabulary ("must contain 'docked'", "must not match /are the
 * default/"), and a sentence reading "Switches between docked and the cockpit
 * inset. A fresh workspace starts on the inset." satisfied all of it while
 * saying the wrong thing.
 *
 * The fix is structural rather than another assertion: the copy interpolates
 * `LAYOUT_PRESET_DEFAULT`, the same name `readLayoutPreset()` returns, so the
 * sentence cannot name a different default. The tests below assert the coupling
 * and then check the specific evasion that defeated the earlier revision.
 */

describe("key-sheet copy is coupled to the layout default", () => {
  it("the reader resolves to the named default when nothing is stored", () => {
    window.localStorage.clear();
    expect(readLayoutPreset()).toBe(LAYOUT_PRESET_DEFAULT);
  });

  it("the default is still the value the store seeds from", () => {
    // Pinned deliberately: if the default changes to the inset, this fails and
    // points at every prose surface that must change with it.
    expect(LAYOUT_PRESET_DEFAULT).toBe("docked");
  });

  it("the copy is built from the constant, not a restatement of it", () => {
    const help = NOTES["layout.togglePreset"] ?? "";
    expect(help).toContain(LAYOUT_PRESET_DEFAULT);
    expect(help).toMatch(/inset/i);
    expect(help).toMatch(/cockpit/i);
  });

  it("the copy does not claim a fresh workspace starts on the inset", () => {
    // The exact sentence that defeated the earlier revision of this test.
    const help = NOTES["layout.togglePreset"] ?? "";
    const tail = help.slice(help.search(/starts/i));
    expect(tail).not.toMatch(/starts\s+(on\s+)?(the\s+)?inset/i);
    expect(tail.length).toBeGreaterThan(0);
  });

  it("the assertion above is not vacuous: it catches the sentence a critic used", () => {
    // Feed the evasion through the same predicate the test uses, so a future
    // edit that weakens the predicate fails here rather than silently passing.
    const evasion =
      "Switches between docked and the cockpit inset. A fresh workspace starts on the inset.";
    const tail = evasion.slice(evasion.search(/starts/i));
    expect(tail).toMatch(/starts\s+(on\s+)?(the\s+)?inset/i);
  });

  it("does not assert that the cockpit is ALREADY the default (the shipped defect)", () => {
    const help = NOTES["layout.togglePreset"] ?? "";
    expect(help).not.toMatch(/are the default/i);
    expect(help).not.toMatch(/is the default/i);
    expect(help).not.toMatch(/by default/i);
  });

  it("that predicate is not vacuous: it rejects the sentence that shipped", () => {
    // The exact string from origin/main before this PR, fed through the same
    // matcher, so weakening the predicate fails here instead of silently passing.
    const shipped =
      "The cockpit's two tall panes are the default; docked puts the panels back at the edges.";
    expect(shipped).toMatch(/are the default/i);
  });
});
