import { describe, expect, it } from "vitest";

import { panelHandleChromeClasses } from "./PanelHandle";

describe("PanelHandle - FEEL-S2 chrome", () => {
  it("floating handles carry press hover-lift and a base shadow", () => {
    const cls = panelHandleChromeClasses(true, true);
    expect(cls).toContain("cursor-grab");
    expect(cls).toContain("shadow-z1");
    expect(cls).toContain("hover:-translate-x-[2px]");
    expect(cls).toContain("hover:-translate-y-[2px]");
    expect(cls).toContain("hover:shadow-z3");
  });

  it("docked handles stay flat and do not lift on hover", () => {
    const cls = panelHandleChromeClasses(false, true);
    expect(cls).not.toContain("cursor-grab");
    expect(cls).not.toContain("shadow-z1");
    expect(cls).not.toContain("hover:-translate");
    expect(cls).not.toContain("hover:shadow-z3");
  });

  it("unfocused handles keep the existing opacity cue", () => {
    expect(panelHandleChromeClasses(false, false)).toContain("opacity-90");
  });
});
