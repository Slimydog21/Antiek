import { describe, expect, it, vi } from "vitest";
import type { Editor } from "@tiptap/react";

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
  function fakeEditor(prefix: string, fullText: string): Editor {
    const pos = prefix.length + 1;
    return {
      state: {
        selection: {
          empty: true,
          $from: {
            parent: { isTextblock: true },
            start: () => 1,
            pos,
          },
        },
        doc: {
          textBetween: (from: number, to: number) => fullText.slice(from - 1, to - 1),
        },
      },
      getText: () => fullText,
      commands: { insertContent: vi.fn() },
    } as unknown as Editor;
  }

  it("does not call completeInline when prefix is whitespace-only", async () => {
    const complete = vi.fn();
    const storage: InlineCompleteStorage = { pending: false };
    const editor = fakeEditor("   ", "   ");

    await runInlineComplete(editor, storage, complete);

    expect(complete).not.toHaveBeenCalled();
    expect(storage.pending).toBe(false);
  });

  it("ignores a second trigger while pending (no duplicate call)", async () => {
    let resolveFirst!: () => void;
    const first = new Promise<{ text: string }>((r) => {
      resolveFirst = () => r({ text: "x" });
    });
    const complete = vi.fn(() => first);
    const storage: InlineCompleteStorage = { pending: false };
    const editor = fakeEditor("Hello", "Hello world");

    const p1 = runInlineComplete(editor, storage, complete);
    expect(shouldRequestCompletion("Hello", storage.pending)).toBe(false);
    const p2 = runInlineComplete(editor, storage, complete);

    resolveFirst();
    await Promise.all([p1, p2]);

    expect(complete).toHaveBeenCalledTimes(1);
    expect(storage.pending).toBe(false);
  });

  it("inserts continuation text on success", async () => {
    const complete = vi.fn().mockResolvedValue({ text: " there" });
    const storage: InlineCompleteStorage = { pending: false };
    const insertContent = vi.fn();
    const editor = {
      ...fakeEditor("Hi", "Hi"),
      commands: { insertContent },
    } as unknown as Editor;

    await runInlineComplete(editor, storage, complete);

    expect(complete).toHaveBeenCalledWith({
      prefix: "Hi",
      document_context: "Hi",
    });
    expect(insertContent).toHaveBeenCalledWith(" there");
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