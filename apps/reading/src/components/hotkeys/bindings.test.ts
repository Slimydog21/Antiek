import { describe, it, expect } from "vitest";

import {
  normalizeBinding,
  isChord,
  formatBinding,
  ariaBinding,
  detectConflict,
  isBlockingConflict,
  reservedReason,
  BUILTIN_BINDINGS,
  PRODUCT_BINDINGS,
  fixedBindings,
  bindingForProduct,
} from "./bindings";

describe("normalizeBinding", () => {
  it("canonicalises combo case + spacing + modifier order", () => {
    expect(normalizeBinding("Mod + K")).toBe("mod+k");
    expect(normalizeBinding("Shift+Mod+P")).toBe("mod+shift+p");
    expect(normalizeBinding("MOD+SHIFT+p")).toBe("mod+shift+p");
  });

  it("canonicalises chords by collapsing whitespace", () => {
    expect(normalizeBinding("G   R")).toBe("g r");
    expect(normalizeBinding(" g  i ")).toBe("g i");
  });
});

describe("isChord", () => {
  it("distinguishes chords from combos", () => {
    expect(isChord("g r")).toBe(true);
    expect(isChord("mod+k")).toBe(false);
    expect(isChord("?")).toBe(false);
  });
});

describe("formatBinding / ariaBinding", () => {
  it("formats combos with glyphs and chords with 'then'", () => {
    // glyph for mod is platform-dependent; assert the structure not the glyph.
    expect(formatBinding("g r")).toContain(" then ");
    expect(formatBinding("g r")).toContain("G");
    expect(formatBinding("g r")).toContain("R");
    expect(formatBinding("mod+shift+p")).toContain("⇧");
    expect(formatBinding("mod+shift+p")).toContain("P");
  });

  it("aria form uses words, not glyphs", () => {
    expect(ariaBinding("g r")).toBe("G then R");
    const combo = ariaBinding("mod+shift+p");
    expect(combo).toContain("Shift");
    expect(combo).toContain("P");
    expect(combo).not.toContain("⇧");
  });
});

describe("reservedReason", () => {
  it("flags browser/OS-eaten combos", () => {
    expect(reservedReason("mod+n")).toMatch(/new window/i);
    expect(reservedReason("Mod+T")).toMatch(/new tab/i);
    expect(reservedReason("g j")).toBeNull();
  });
});

describe("detectConflict + precedence", () => {
  it("BLOCKS a custom binding that shadows a built-in (custom-vs-builtin)", () => {
    // mod+k is the command palette built-in.
    const c = detectConflict("mod+k", []);
    expect(c).not.toBeNull();
    expect(c!.kind).toBe("builtin");
    expect(isBlockingConflict(c)).toBe(true);
  });

  it("BLOCKS a custom binding that shadows a product chord", () => {
    // "g r" is the Research product binding.
    const c = detectConflict("g r", []);
    expect(c).not.toBeNull();
    expect(["product", "builtin"]).toContain(c!.kind); // g r is both home builtin + research product
    expect(isBlockingConflict(c)).toBe(true);
  });

  it("BLOCKS a reserved browser combo", () => {
    const c = detectConflict("mod+t", []);
    expect(c!.kind).toBe("reserved");
    expect(isBlockingConflict(c)).toBe(true);
  });

  it("treats custom-vs-custom as OVERRIDABLE (not blocking)", () => {
    const existing = [{ id: "a", spec: "j" }];
    const c = detectConflict("j", existing, "b");
    expect(c).not.toBeNull();
    expect(c!.kind).toBe("custom");
    expect(c!.withId).toBe("a");
    expect(isBlockingConflict(c)).toBe(false);
  });

  it("does not conflict with itself (selfId excluded)", () => {
    const existing = [{ id: "a", spec: "j" }];
    expect(detectConflict("j", existing, "a")).toBeNull();
  });

  it("allows a free key", () => {
    expect(detectConflict("g j", [])).toBeNull();
  });
});

describe("binding tables", () => {
  it("has the load-bearing built-ins", () => {
    const ids = BUILTIN_BINDINGS.map((b) => b.id);
    expect(ids).toContain("palette");
    expect(ids).toContain("help");
    expect(ids).toContain("aisidecar");
  });

  it("every product is reachable by a unique non-reserved binding", () => {
    const specs = new Set<string>();
    for (const p of PRODUCT_BINDINGS) {
      const n = normalizeBinding(p.spec);
      expect(reservedReason(n)).toBeNull();
      specs.add(n);
    }
    expect(specs.size).toBe(PRODUCT_BINDINGS.length);
  });

  it("fixed bindings contain no internal duplicate specs (except g r alias)", () => {
    const seen = new Map<string, number>();
    for (const b of fixedBindings()) {
      const n = normalizeBinding(b.spec);
      seen.set(n, (seen.get(n) ?? 0) + 1);
    }
    // g r is intentionally shared by go-home (builtin) + research/home (product).
    for (const [spec, count] of seen) {
      if (spec === "g r") {
        expect(count).toBeGreaterThanOrEqual(2);
      } else {
        expect(count).toBe(1);
      }
    }
  });

  it("bindingForProduct resolves product + sub-action rows", () => {
    expect(bindingForProduct("read")?.spec).toBe("g e");
    expect(bindingForProduct("research", "new")?.spec).toBe("g c");
  });
});

describe("route + label honesty (SPR-08 sharpen)", () => {
  it("Home and Research are DISTINCT destinations (no duplicate doing the same thing)", () => {
    const home = bindingForProduct("home");
    const research = bindingForProduct("research");
    expect(home?.route).toBe("/home");
    expect(research?.route).toBe("/");
    expect(home?.route).not.toBe(research?.route);
  });

  it("More carries NO route — it opens the launcher, it does not navigate", () => {
    const more = bindingForProduct("more");
    expect(more).toBeTruthy();
    expect(more?.route).toBeUndefined();
  });

  it("the sub-research label no longer claims to 'start a new research' (it goes to the Research home)", () => {
    const sub = bindingForProduct("research", "new");
    expect(sub?.route).toBe("/");
    expect(sub?.label).not.toMatch(/start a new research/i);
    expect(sub?.label).toMatch(/research home/i);
  });
});

describe("glyphForToken named-key glyphs (SPR-08 sharpen — no dead ternary)", () => {
  it("renders named multi-char keys as short glyphs, not shouty all-caps words", () => {
    // Custom combos can be Enter/Escape/Arrow* — they must not render "ENTER".
    expect(formatBinding("mod+enter")).toContain("↵");
    expect(formatBinding("mod+enter")).not.toContain("ENTER");
    expect(formatBinding("alt+arrowup")).toContain("↑");
    expect(formatBinding("alt+escape")).toContain("Esc");
    expect(formatBinding("alt+escape")).not.toContain("ESCAPE");
  });

  it("still upper-cases single printable keys", () => {
    expect(formatBinding("g r")).toContain("R");
  });
});
