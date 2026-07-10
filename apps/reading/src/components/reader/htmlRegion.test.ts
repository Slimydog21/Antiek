import { describe, expect, it } from "vitest";
import { regionFromRange, resolveHtmlRegion } from "./htmlRegion";

function fixture(text = "same first same last") {
  document.body.innerHTML = `<main id="reader"><p id="antiek-anchor-a" data-source-page="7">${text}</p></main>`;
  return document.getElementById("reader") as HTMLElement;
}

describe("HTML region anchors", () => {
  it("uses exact DOM boundaries when text repeats", () => {
    const reader = fixture();
    const text = reader.querySelector("p")!.firstChild!;
    const range = document.createRange();
    range.setStart(text, 11); range.setEnd(text, 15);
    expect(regionFromRange(reader, range)).toMatchObject({ charStart: 11, charEnd: 15, exact: "same", sourcePage: 7 });
  });

  it("resolves after reload and reports drift after preceding insertion", () => {
    const reader = fixture();
    const text = reader.querySelector("p")!.firstChild!;
    const range = document.createRange(); range.setStart(text, 11); range.setEnd(text, 15);
    const region = regionFromRange(reader, range)!;
    expect(resolveHtmlRegion(reader, region).status).toBe("resolved");
    reader.querySelector("p")!.textContent = `new ${reader.querySelector("p")!.textContent}`;
    expect(resolveHtmlRegion(reader, region).status).toBe("drift");
  });

  it("reports unresolved rather than guessing", () => {
    const reader = fixture("same same");
    expect(resolveHtmlRegion(reader, { anchorId: "antiek-anchor-a", charStart: 20, charEnd: 24, exact: "same", prefix: "", suffix: "", sourcePage: null })).toEqual({ status: "unresolved", reason: "ambiguous" });
    expect(resolveHtmlRegion(reader, { anchorId: "antiek-anchor-gone", charStart: 0, charEnd: 1, exact: "x", prefix: "", suffix: "", sourcePage: null })).toEqual({ status: "unresolved", reason: "anchor-missing" });
  });
});
