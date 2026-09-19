import { afterEach, describe, expect, it } from "vitest";

import {
  clearReadingFocus,
  formatReadingFocusSystemContext,
  getReadingFocus,
  setReadingFocus,
} from "./readingFocus";

afterEach(() => {
  clearReadingFocus();
});

describe("readingFocus SERVABLE mount", () => {
  it("publishes page text only when servable", () => {
    setReadingFocus({
      documentId: "doc-1",
      pageIndex: 2,
      title: "Meditations",
      pageText: "SECRET-GATED",
      servable: false,
    });
    const f = getReadingFocus();
    expect(f?.pageText).toBeNull();
    expect(f?.servable).toBe(false);
    const ctx = formatReadingFocusSystemContext();
    expect(ctx).toMatch(/gated/i);
    expect(ctx).not.toContain("SECRET-GATED");
  });

  it("formats SERVABLE page for system_context", () => {
    setReadingFocus({
      documentId: "doc-servable",
      pageIndex: 0,
      title: "Open Book",
      pageText: "The aurora compounds over winters.",
      servable: true,
    });
    const ctx = formatReadingFocusSystemContext();
    expect(ctx).toMatch(/SERVABLE/);
    expect(ctx).toContain("doc-servable");
    expect(ctx).toContain("The aurora compounds over winters.");
    expect(ctx).toContain("page_index: 0");
  });
});
