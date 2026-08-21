import { describe, expect, it } from "vitest";

import { anchorFromRange } from "./artifactFeedbackSelection";

describe("artifact feedback selection anchors", () => {
  it("binds one node selection using NFC Unicode-scalar offsets", async () => {
    const card = document.createElement("p");
    card.dataset.antiekNodeId = "insight-1";
    card.dataset.antiekSourceDocumentId = "doc-1";
    card.textContent = "Cafe\u0301 🧪 result";
    document.body.append(card);
    const text = card.firstChild;
    if (!(text instanceof Text)) throw new Error("test text node missing");
    const range = document.createRange();
    range.setStart(text, 6);
    range.setEnd(text, 8);

    await expect(anchorFromRange(range)).resolves.toEqual({
      normalization: "unicode-nfc-v1",
      node_id: "insight-1",
      source_document_id: "doc-1",
      node_text_sha256: "6246e2cb27b90a8eb4202177305a17ac116830d4c5997e4600a9848b07dc2418",
      start_scalar: 5,
      end_scalar: 6,
      quote: "🧪",
      prefix: "Café ",
      suffix: " result",
    });
  });

  it("refuses a selection spanning two semantic nodes", async () => {
    const first = document.createElement("p");
    first.dataset.antiekNodeId = "insight-1";
    first.textContent = "first";
    const second = document.createElement("p");
    second.dataset.antiekNodeId = "insight-2";
    second.textContent = "second";
    document.body.append(first, second);
    const range = document.createRange();
    range.setStart(first.firstChild ?? first, 0);
    range.setEnd(second.firstChild ?? second, 2);

    await expect(anchorFromRange(range)).resolves.toBeNull();
  });
});
