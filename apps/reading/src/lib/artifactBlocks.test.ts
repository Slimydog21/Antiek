import { describe, expect, it } from "vitest";

import { artifactKindToBlockKind } from "./artifactBlocks";

describe("artifactKindToBlockKind", () => {
  it("maps question to open_question", () => {
    expect(artifactKindToBlockKind("question")).toBe("open_question");
  });
  it("maps insight to insight", () => {
    expect(artifactKindToBlockKind("insight")).toBe("insight");
  });
  it("falls back to claim", () => {
    expect(artifactKindToBlockKind("synthesis")).toBe("claim");
  });
});