import { afterEach, describe, expect, it, vi } from "vitest";
import { Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";

import {
  capDocumentContext,
  extractBlockPrefix,
  runInlineComplete,
  shouldRequestCompletion,
  type InlineCompleteStorage,
} from "./InlineComplete";

describe("shouldRequestCompletion", () => {
  it("rejects empty or whitespace-only prefix", () => {
    expect(shouldRequestCompletion("", false)).toBe(false);
    expect(shouldRequestCompletion("   \n", false)).toBe(false);
  });

  it("rejects when a request is already pending", () => {
    expect(shouldRequestCompletion("hello", true)).toBe(false);
  });

  it("allows a non-empty prefix when not pending", () => {
    expect(shouldRequestCompletion("hello", false)).toBe(true);
  });
});

describe("capDocumentContext", () => {
  it("caps document context to the configured maximum", () => {
    const long = "a".repeat(5000);
    expect(capDocumentContext(long).length).toBe(4000);
  });
});

describe("runInlineComplete", () => {
  const editors: Editor[] = [];
  function makeEditor(text: string) {
    const editor = new Editor({
      element: document.createElement("div"),
      extensions: [StarterKit],
      content: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text }] }] },
    });
    editor.commands.setTextSelection(text.length + 1);
    editors.push(editor);
    return editor;
  }
  afterEach(() => { for (const editor of editors.splice(0)) editor.destroy(); });

  function delayedCompletion() {
    let resolve = (_value: { text: string }): void => { throw new Error("Promise not initialized"); };
    const promise = new Promise<{ text: string }>((res) => { resolve = res; });
    return { complete: vi.fn(() => promise), resolve };
  }

  it("does not call completeInline when prefix is whitespace-only", async () => {
    const complete = vi.fn();
    const storage: InlineCompleteStorage = { pending: false };
    await runInlineComplete(makeEditor("   "), storage, complete);
    expect(complete).not.toHaveBeenCalled();
    expect(storage.pending).toBe(false);
  });

  it("ignores a second trigger while pending", async () => {
    const { complete, resolve } = delayedCompletion();
    const storage: InlineCompleteStorage = { pending: false };
    const editor = makeEditor("Hello");
    const first = runInlineComplete(editor, storage, complete);
    const second = runInlineComplete(editor, storage, complete);
    expect(storage.pending).toBe(true);
    resolve({ text: " there" });
    await Promise.all([first, second]);
    expect(complete).toHaveBeenCalledTimes(1);
    expect(editor.getText()).toBe("Hello there");
    expect(storage.pending).toBe(false);
  });

  it("inserts continuation text into the unchanged request context", async () => {
    const complete = vi.fn().mockResolvedValue({ text: " there" });
    const storage: InlineCompleteStorage = { pending: false };
    const editor = makeEditor("Hi");
    await runInlineComplete(editor, storage, complete);
    expect(complete).toHaveBeenCalledWith({ prefix: "Hi", document_context: "Hi" });
    expect(editor.getText()).toBe("Hi there");
  });

  it.each(["readonly", "destroyed"])("does not request a completion from a %s editor", async (state) => {
    const editor = makeEditor("Hello");
    if (state === "readonly") editor.setEditable(false, false);
    else editor.destroy();
    const complete = vi.fn().mockResolvedValue({ text: " stale" });
    await runInlineComplete(editor, { pending: false }, complete);
    expect(complete).not.toHaveBeenCalled();
  });

  it.each(["readonly", "destroyed", "edited", "selection moved", "replaced document"])("drops a late completion after the editor is %s", async (change) => {
    const editor = makeEditor("Hello");
    const { complete, resolve } = delayedCompletion();
    const storage: InlineCompleteStorage = { pending: false };
    const pending = runInlineComplete(editor, storage, complete);
    if (change === "readonly") editor.setEditable(false, false);
    if (change === "destroyed") editor.destroy();
    if (change === "edited") editor.commands.insertContent(" edited");
    if (change === "selection moved") editor.commands.setTextSelection(1);
    if (change === "replaced document") editor.commands.setContent("<p>A different draft.</p>");
    const currentText = editor.isDestroyed ? null : editor.getText();
    const commands = vi.spyOn(editor, "commands", "get");
    resolve({ text: " stale completion" });
    await pending;
    expect(commands).not.toHaveBeenCalled();
    if (currentText !== null) expect(editor.getText()).toBe(currentText);
    expect(storage.pending).toBe(false);
  });
});

describe("extractBlockPrefix", () => {
  it("returns empty when selection is not collapsed", () => {
    const state = {
      selection: { empty: false, $from: { parent: { isTextblock: true }, start: () => 0, pos: 1 } },
      doc: { textBetween: () => "x" },
    };
    expect(extractBlockPrefix(state as never)).toBe("");
  });
});