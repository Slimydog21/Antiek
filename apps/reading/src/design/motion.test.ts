import { describe, expect, it } from "vitest";

import { cardLift, press } from "./motion";

describe("motion primitives - reduced-motion transform suppression", () => {
  it("keeps press tactile affordances but suppresses hover/active travel", () => {
    expect(press).toContain("hover:shadow-z3");
    expect(press).toContain("motion-reduce:hover:translate-x-0");
    expect(press).toContain("motion-reduce:hover:translate-y-0");
    expect(press).toContain("motion-reduce:active:translate-x-0");
    expect(press).toContain("motion-reduce:active:translate-y-0");
  });

  it("keeps card shadow lift but suppresses reduced-motion card travel", () => {
    expect(cardLift).toContain("group-hover:shadow-z2");
    expect(cardLift).toContain("motion-reduce:group-hover:translate-y-0");
  });
});
