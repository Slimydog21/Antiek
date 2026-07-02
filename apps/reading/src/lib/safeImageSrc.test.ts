import { describe, expect, it } from "vitest";

import { safeImageSrc } from "./safeImageSrc";

describe("safeImageSrc", () => {
  it.each([
    [" https://img.example/notebook.png ", "https://img.example/notebook.png"],
    ["http://img.example/notebook.png", "http://img.example/notebook.png"],
    [" data:image/png;base64,AAAA ", "data:image/png;base64,AAAA"],
  ])("accepts safe image sources: %s", (input, expected) => {
    expect(safeImageSrc(input)).toBe(expected);
  });

  it.each([
    "javascript:alert(1)",
    "data:text/html,owned",
    "/relative/notebook.png",
    "img.example/notebook.png",
    " ",
    null,
    { src: "https://img.example/notebook.png" },
  ])("rejects unsafe image sources: %s", (input) => {
    expect(safeImageSrc(input)).toBeNull();
  });
});
