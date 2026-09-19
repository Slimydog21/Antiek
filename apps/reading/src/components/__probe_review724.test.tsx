import { describe, expect, it } from "vitest";
import { validateBornAntiekHtml } from "./HtmlReader";

// Review probes (session d4507b63): vectors NOT covered by the PR's test matrix.
describe("review probes", () => {
  it("PROBE table background attribute (legacy URL presentational hint)", () => {
    let threw = false;
    try { validateBornAntiekHtml(`<table background="https://evil.invalid/beacon"><tr><td>x</td></tr></table>`); } catch { threw = true; }
    console.log("table-background rejected:", threw);
    expect(true).toBe(true);
  });
  it("PROBE frameset/frame", () => {
    let threw = false; let out = "";
    try { out = validateBornAntiekHtml(`<frameset><frame></frameset>`); } catch { threw = true; }
    console.log("frameset rejected:", threw, "| output:", JSON.stringify(out));
    expect(true).toBe(true);
  });
  it("PROBE name attribute (DOM clobbering) and contenteditable", () => {
    let threwName = false, threwCe = false;
    try { validateBornAntiekHtml(`<img name="cookie">`); } catch { threwName = true; }
    try { validateBornAntiekHtml(`<p contenteditable="">x</p>`); } catch { threwCe = true; }
    console.log("img-name rejected:", threwName, "| contenteditable rejected:", threwCe);
    expect(true).toBe(true);
  });
  it("PROBE body background + data-URL-free img alt-only", () => {
    let threw = false;
    try { validateBornAntiekHtml(`<td background="https://evil.invalid/b">x</td>`); } catch { threw = true; }
    console.log("td-background rejected:", threw);
    expect(true).toBe(true);
  });
});
