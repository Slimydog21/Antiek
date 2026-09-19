import { describe, expect, it } from "vitest";
import { validateBornAntiekHtml } from "./HtmlReader";
describe("probe2 - does the un-gated URL attr survive into rendered output", () => {
  it("background attr re-serialized into injected HTML", () => {
    const out = validateBornAntiekHtml(`<table background="https://evil.invalid/beacon.png"><tbody><tr><td>x</td></tr></tbody></table>`);
    console.log("OUTPUT:", out);
    console.log("CONTAINS evil.invalid:", out.includes("evil.invalid"));
  });
  it("name attr (DOM clobber) survives", () => {
    const out = validateBornAntiekHtml(`<img name="attributes"><p id="antiek-anchor-x">y</p>`);
    console.log("NAME OUTPUT:", out);
  });
});
