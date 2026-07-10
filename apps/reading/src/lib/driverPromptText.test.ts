import { describe, expect, it } from "vitest";
import {
  composeDriverPromptText,
  countPublicationRefs,
} from "./driverPromptText";

describe("composeDriverPromptText (qr)", () => {
  it("joins body and publication refs", () => {
    const out = composeDriverPromptText(
      "What is attention?",
      "arxiv:1706.03762",
    );
    expect(out).toMatch(/What is attention\?/);
    expect(out).toMatch(/Publication refs:/);
    expect(out).toMatch(/arxiv:1706\.03762/);
  });

  it("omits empty parts without inventing content", () => {
    expect(composeDriverPromptText("  hello  ", "  ")).toBe("hello");
    expect(composeDriverPromptText("", "arxiv:1")).toBe(
      "Publication refs:\narxiv:1",
    );
    expect(composeDriverPromptText("  ", null)).toBe("");
  });
});

describe("countPublicationRefs (ahg/ahp)", () => {
  it("counts non-empty lines only", () => {
    expect(countPublicationRefs("")).toBe(0);
    expect(countPublicationRefs(null)).toBe(0);
    expect(countPublicationRefs("arxiv:1706.03762")).toBe(1);
    expect(
      countPublicationRefs("arxiv:1706.03762\n\narxiv:1810.04805\n  \n"),
    ).toBe(2);
  });
});
