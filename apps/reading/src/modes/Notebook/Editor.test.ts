import { describe, expect, it } from "vitest";

import { notebookContentEndpoint } from "./Editor";

describe("NotebookEditor autosave endpoint", () => {
  it("encodes notebook ids before building the content autosave URL", () => {
    expect(notebookContentEndpoint("nb dirty/1")).toBe(
      "/notebooks/nb%20dirty%2F1/content",
    );
  });
});
