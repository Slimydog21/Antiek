import { describe, expect, it } from "vitest";

import { NOTES, layoutPresetHelp } from "./keymapView";
import { LAYOUT_PRESET_DEFAULT, readLayoutPreset } from "../../workspace/persistence";

/**
 * The key sheet's layout row must not contradict the layout default.
 *
 * The shipped copy said "The cockpit's two tall panes are the default; docked
 * puts the panels back at the edges". `readLayoutPreset()` returns "docked" on a
 * miss, a parse error, a schema-version mismatch or an unknown value, and
 * `WorkspaceStore.ts` seeds its `layoutPreset` from that reader - so a fresh
 * workspace really does start docked, and the sheet told the operator the
 * opposite.
 *
 * ── WHY THIS FILE IS SHAPED THE WAY IT IS ─────────────────────────────────
 * [1] The first revision asserted vocabulary ("must contain 'docked'", "must not
 *     match /are the default/"). A critic defeated it with a sentence that named
 *     the wrong preset and satisfied every assertion.
 * [2] The second revision interpolated the constant into a literal and matched
 *     regexes on the result. The same critic defeated THAT, with "a fresh
 *     workspace starts on the two tall panes" - which names the inset without
 *     using the word "inset", and which the regex never saw.
 * [3] This revision stops trying to read prose. The note IS
 *     `layoutPresetHelp(LAYOUT_PRESET_DEFAULT)`, and the tests assert that
 *     equality. A hand-written sentence claiming a different preset cannot equal
 *     it, whatever words it uses. Equality is checkable; meaning is not.
 */

describe("key-sheet copy is a function of the layout default", () => {
  it("the reader resolves to the named default when nothing is stored", () => {
    window.localStorage.clear();
    expect(readLayoutPreset()).toBe(LAYOUT_PRESET_DEFAULT);
  });

  it("the default is still docked - pinned, because a change here changes prose", () => {
    expect(LAYOUT_PRESET_DEFAULT).toBe("docked");
  });

  it("the note is exactly the template applied to the real default", () => {
    expect(NOTES["layout.togglePreset"]).toBe(layoutPresetHelp(LAYOUT_PRESET_DEFAULT));
  });

  it("the template genuinely depends on its argument", () => {
    // Without this, the equality above could hold for a constant string and the
    // whole coupling would be decorative.
    const other = layoutPresetHelp("omarchy-inset");
    expect(other).not.toBe(layoutPresetHelp("docked"));
    expect(other).toContain("omarchy-inset");
  });

  it("rejects the sentence a critic used to defeat the previous revision", () => {
    // [2]'s counterexample. It names the inset without the word "inset", so the
    // old regex passed it. Equality rejects it because it is not HELP(DEFAULT).
    const evasion =
      "Switches between docked and the cockpit inset. A fresh workspace starts on the two tall panes.";
    expect(evasion).not.toBe(layoutPresetHelp(LAYOUT_PRESET_DEFAULT));
    expect(NOTES["layout.togglePreset"]).not.toBe(evasion);
  });

  it("rejects the sentence that shipped", () => {
    const shipped =
      "The cockpit's two tall panes are the default; docked puts the panels back at the edges.";
    expect(NOTES["layout.togglePreset"]).not.toBe(shipped);
  });
});
