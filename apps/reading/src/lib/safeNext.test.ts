import { expect, it } from "vitest";
import { safeNext } from "./safeNext";

it.each([
  undefined, null, 4, { pathname: "/notes" }, "", "notes", "https://outside.example",
  "javascript:alert(1)", "//outside.example", "/\\outside.example", "/notes\\more",
  "/notes\nmore", "/notes\tmore", "/notes\u0000", "/notes\u007f",
])("falls back for an invalid destination %j", (value) => {
  expect(safeNext(value)).toBe("/");
});

it.each(["/", "/notes?q=one#two", "/notes/日本語", "/notes/a%20b", "/notes?url=https://example.test"])(
  "preserves a root-relative destination %s", (value) => {
    expect(safeNext(value)).toBe(value);
  },
);
