/** composerKeys.test.ts — SPR-07 invariant 12 (pattern 9), the Escape ladder (pattern 10) and the digit rule (fix 6). */
import { describe, expect, it } from "vitest";

import { ESCAPE_LADDER, cannedPromptForDigit, nextEscapeRung, resolveComposerKey } from "./composerKeys";

const base = { shift: false, isComposing: false, pickerOpen: false, optionCount: 0, highlighted: -1 };

describe("resolveComposerKey", () => {
  it.each([
    [{ ...base, key: "Enter" }, "send"],
    [{ ...base, key: "Enter", shift: true }, "newline"],
    [{ ...base, key: "Enter", isComposing: true }, "none"],
    [{ ...base, key: "Enter", pickerOpen: true, optionCount: 3, highlighted: 0 }, "complete"],
    [{ ...base, key: "Tab", pickerOpen: true, optionCount: 3, highlighted: 0 }, "complete"],
    [{ ...base, key: "Escape", pickerOpen: true, optionCount: 3, highlighted: 0 }, "dismiss"],
    [{ ...base, key: "ArrowUp", pickerOpen: true, optionCount: 3, highlighted: 0 }, "move-up"],
    [{ ...base, key: "a" }, "none"],
  ])("%j ⇒ %s", (input, action) => {
    expect(resolveComposerKey(input).action).toBe(action);
  });

  it("ArrowDown at the last option wraps to the first", () => {
    const r = resolveComposerKey({ ...base, key: "ArrowDown", pickerOpen: true, optionCount: 3, highlighted: 2 });
    expect(r).toEqual({ action: "move-down", highlighted: 0 });
    expect(resolveComposerKey({ ...base, key: "ArrowUp", pickerOpen: true, optionCount: 3, highlighted: 0 }).highlighted).toBe(2);
  });
});

describe("the Escape ladder", () => {
  it("is picker → recording → chip → blur → close", () => {
    expect(ESCAPE_LADDER).toEqual(["picker", "recording", "chip", "blur", "close"]);
    expect(nextEscapeRung({ pickerOpen: true, recording: true, hasChip: true, composerFocused: true })).toBe("picker");
    expect(nextEscapeRung({ pickerOpen: false, recording: true, hasChip: true, composerFocused: true })).toBe("recording");
    expect(nextEscapeRung({ pickerOpen: false, recording: false, hasChip: true, composerFocused: true })).toBe("chip");
    expect(nextEscapeRung({ pickerOpen: false, recording: false, hasChip: false, composerFocused: true })).toBe("blur");
    expect(nextEscapeRung({ pickerOpen: false, recording: false, hasChip: false, composerFocused: false })).toBe("close");
  });
});

describe("cannedPromptForDigit", () => {
  it("picks 1|2|3 only when BOTH the thread and the draft are empty and the draft is unmodified", () => {
    const clean = { threadEmpty: true, draftEmpty: true, modified: false };
    expect(cannedPromptForDigit("1", clean)).toBe(1);
    expect(cannedPromptForDigit("3", clean)).toBe(3);
    expect(cannedPromptForDigit("4", clean)).toBeNull();
    expect(cannedPromptForDigit("1", { ...clean, draftEmpty: false })).toBeNull();
    expect(cannedPromptForDigit("1", { ...clean, threadEmpty: false })).toBeNull();
    expect(cannedPromptForDigit("1", { ...clean, modified: true })).toBeNull();
  });
});
