import { describe, expect, it } from "vitest";

import { ROUTE_INDEX, documentPalettePath } from "./CommandPalette";

describe("CommandPalette document taxonomy", () => {
  it("pins the research document route and HTML workspace copy", () => {
    const route = ROUTE_INDEX.find((entry) => entry.id === "route:documents");
    expect(route).toMatchObject({
      title: "Research documents",
      path: "/documents",
    });
    expect(route?.subtitle).toMatch(/HTML document reader and research workspace/);
    expect(ROUTE_INDEX.some((entry) => entry.path === "/wrestle")).toBe(false);
  });

  it("builds encoded canonical paths for document results", () => {
    expect(documentPalettePath("doc 1/α")).toBe("/documents/doc%201%2F%CE%B1");
  });
});
