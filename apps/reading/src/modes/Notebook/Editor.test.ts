import { describe, expect, it } from "vitest";

import { notebookContentEndpoint, normalizeNotebookId } from "./Editor";

describe("normalizeNotebookId", () => {
  it("trims stored notebook ids and falls back to scratch for blanks", () => {
    expect(normalizeNotebookId("  research-notes  ")).toBe("research-notes");
    expect(normalizeNotebookId("   ")).toBe("scratch");
    expect(normalizeNotebookId(null)).toBe("scratch");
    expect(normalizeNotebookId(undefined)).toBe("scratch");
  });
});

describe("NotebookEditor autosave endpoint", () => {
  it("encodes notebook ids before building the content autosave URL", () => {
    expect(notebookContentEndpoint("nb dirty/1")).toBe(
      "/notebooks/nb%20dirty%2F1/content",
    );
  });

  it("normalizes notebook ids before building the content autosave URL", () => {
    expect(notebookContentEndpoint("  nb dirty/1  ")).toBe(
      "/notebooks/nb%20dirty%2F1/content",
    );
    expect(notebookContentEndpoint("   ")).toBe("/notebooks/scratch/content");
  });
});
