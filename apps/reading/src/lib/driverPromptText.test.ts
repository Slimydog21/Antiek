import { describe, expect, it } from "vitest";
import { composeDriverPromptText } from "./driverPromptText";

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
