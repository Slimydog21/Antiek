import { describe, expect, it } from "vitest";

import { readerChunkIdForRange } from "./readerChunkProvenance";

function fixture() {
  const scope = document.createElement("article");
  scope.innerHTML =
    '<section data-akb-chunk-id="chunk-a"><p>Alpha passage</p></section>' +
    '<section data-akb-chunk-id="chunk-b"><p>Beta passage</p></section>';
  document.body.appendChild(scope);
  return scope;
}

describe("readerChunkIdForRange", () => {
  it("returns the authoritative id for a selection inside one chunk", () => {
    const scope = fixture();
    const text = scope.querySelector("p")!.firstChild!;
    const range = document.createRange();
    range.setStart(text, 0);
    range.setEnd(text, 5);
    expect(readerChunkIdForRange(scope, range)).toBe("chunk-a");
    scope.remove();
  });

  it("returns null when a selection crosses chunk boundaries", () => {
    const scope = fixture();
    const text = scope.querySelectorAll("p");
    const range = document.createRange();
    range.setStart(text[0].firstChild!, 0);
    range.setEnd(text[1].firstChild!, 4);
    expect(readerChunkIdForRange(scope, range)).toBeNull();
    scope.remove();
  });

  it("returns null for unanchored reader prose", () => {
    const scope = document.createElement("article");
    scope.textContent = "Unresolved prose";
    document.body.appendChild(scope);
    const range = document.createRange();
    range.selectNodeContents(scope);
    expect(readerChunkIdForRange(scope, range)).toBeNull();
    scope.remove();
  });
});
