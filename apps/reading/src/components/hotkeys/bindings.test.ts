import { describe, it, expect } from "vitest";

import {
  normalizeBinding,
  isChord,
  formatBinding,
  ariaBinding,
  detectConflict,
  isBlockingConflict,
  reservedReason,
  requiresModifierReason,
  BUILTIN_BINDINGS,
  PRODUCT_BINDINGS,
  SUBACTION_BINDINGS,
  fixedBindings,
  bindingForProduct,
  chipBindings,
  SAFE_ASSIGNABLE,
  RESERVED_COMBOS,
} from "./bindings";

describe("normalizeBinding", () => {
  it("canonicalises combo case + spacing + modifier order", () => {
    expect(normalizeBinding("Mod + K")).toBe("mod+k");
    expect(normalizeBinding("Shift+Mod+P")).toBe("mod+shift+p");
    expect(normalizeBinding("MOD+SHIFT+p")).toBe("mod+shift+p");
    expect(normalizeBinding("Mod+E")).toBe("mod+e");
  });

  it("tolerates a stray legacy chord form (for a corrupt persisted blob)", () => {
    // No live binding produces this, but normalize must not throw on it.
    expect(normalizeBinding("G   R")).toBe("g r");
  });
});

describe("isChord — false for every live binding (SPR-08 ripped chords out)", () => {
  it("a combo is never a chord", () => {
    expect(isChord("mod+k")).toBe(false);
    expect(isChord("mod+e")).toBe(false);
    expect(isChord("?")).toBe(false);
  });

  it("still detects a (legacy/corrupt) chord shape so the affordance can reject it", () => {
    expect(isChord("g r")).toBe(true);
  });

  it("EVERY fixedBindings() row is NOT a chord (the core M1 invariant)", () => {
    for (const b of fixedBindings()) {
      expect(isChord(b.spec), `${b.id} (${b.spec}) must not be a chord`).toBe(false);
    }
  });
});

describe("formatBinding / ariaBinding — ⌘ combos, no 'then'", () => {
  it("formats combos with glyphs (no 'then' separator)", () => {
    expect(formatBinding("mod+e")).toContain("E");
    expect(formatBinding("mod+e")).not.toContain("then");
    expect(formatBinding("mod+shift+p")).toContain("⇧");
    expect(formatBinding("mod+shift+p")).toContain("P");
    expect(formatBinding("mod+shift+p")).not.toContain("then");
  });

  it("aria form uses words, not glyphs (mod → Meta-on-mac / Control-elsewhere)", () => {
    // The exact mod word is platform-dependent (Meta vs Control); assert the
    // STRUCTURE + the key, not the platform glyph.
    const e = ariaBinding("mod+e");
    expect(e).toMatch(/^(Meta|Control)\+E$/);
    const combo = ariaBinding("mod+shift+p");
    expect(combo).toMatch(/^(Meta|Control)\+Shift\+P$/);
    expect(combo).toContain("Shift");
    expect(combo).toContain("P");
    expect(combo).not.toContain("⇧");
  });
});

describe("reservedReason — derivation-carrying browser/OS combos", () => {
  it("flags browser/OS-eaten combos with a reason", () => {
    expect(reservedReason("mod+n")).toMatch(/new window/i);
    expect(reservedReason("Mod+T")).toMatch(/new tab/i);
    expect(reservedReason("mod+r")).toMatch(/reload/i);
    expect(reservedReason("mod+s")).toMatch(/save/i);
    expect(reservedReason("mod+1")).toMatch(/tab 1/i);
  });

  it("does NOT flag a free safe combo", () => {
    expect(reservedReason("mod+e")).toBeNull();
    expect(reservedReason("alt+j")).toBeNull();
    expect(reservedReason("mod+i")).toBeNull(); // ⌘I (More) is free + safe
  });

  it("reserves the macOS window-server accelerators ⌘H and ⌘M with a derivation", () => {
    // These guard against a later sprint re-grabbing ⌘M for More (the SPR-08
    // sharpen moved More off ⌘M precisely because the OS owns it).
    expect(reservedReason("mod+h")).toMatch(/hide|window-server/i);
    expect(reservedReason("mod+m")).toMatch(/minimi|window-server/i);
  });

  it("every reserved combo carries a non-empty reason (defensibility)", () => {
    for (const r of RESERVED_COMBOS) {
      expect(r.reason.length, `${r.spec} needs a derivation`).toBeGreaterThan(0);
    }
  });

  it("reserves at least the brief's named browser/OS combos", () => {
    const specs = new Set(RESERVED_COMBOS.map((r) => normalizeBinding(r.spec)));
    for (const must of [
      "mod+w", "mod+t", "mod+n", "mod+r", "mod+l", "mod+q",
      "mod+s", "mod+p", "mod+f", "mod+z", "mod+a", "mod+c", "mod+v",
      "mod+1", "mod+9",
    ]) {
      expect(specs.has(must), `${must} must be reserved`).toBe(true);
    }
  });
});

describe("requiresModifierReason — bare key AND chord both rejected", () => {
  it("rejects a bare single key (footgun)", () => {
    expect(requiresModifierReason("j")).toMatch(/add ⌘|single key/i);
  });
  it("rejects a chord (no sequences after SPR-08)", () => {
    expect(requiresModifierReason("g r")).toMatch(/sequence|single ⌘ combo/i);
  });
  it("accepts a modifier combo", () => {
    expect(requiresModifierReason("mod+e")).toBeNull();
    expect(requiresModifierReason("alt+j")).toBeNull();
  });
});

describe("SAFE_ASSIGNABLE — the bindable range + its derivation", () => {
  it("excludes the reserved letters from the bindable letter set (computed, not hand-listed)", () => {
    // r/t/n/w/s/p/f/l/q/z/a/c/v are all reserved → must NOT be bindable letters.
    // h/m are macOS window-server accelerators (hide-app / minimize-window),
    // reserved in the same class as ⌘Q — they too must NOT be bindable.
    for (const reservedLetter of ["r", "t", "n", "w", "s", "p", "f", "l", "z", "a", "c", "v", "h", "m"]) {
      expect(
        SAFE_ASSIGNABLE.letters.includes(reservedLetter),
        `${reservedLetter} is reserved and must not be a safe letter`,
      ).toBe(false);
    }
    // The letters the products use ARE bindable.
    for (const free of ["j", "e", "y", "u", "o", "i"]) {
      expect(SAFE_ASSIGNABLE.letters.includes(free), `${free} should be safe`).toBe(true);
    }
  });

  it("isWithinRange accepts a single mod-combo, rejects bare keys + chords + no-mod", () => {
    expect(SAFE_ASSIGNABLE.isWithinRange("mod+e")).toBe(true);
    expect(SAFE_ASSIGNABLE.isWithinRange("mod+shift+e")).toBe(true);
    expect(SAFE_ASSIGNABLE.isWithinRange("j")).toBe(false); // bare key
    expect(SAFE_ASSIGNABLE.isWithinRange("g r")).toBe(false); // chord
    expect(SAFE_ASSIGNABLE.isWithinRange("alt+j")).toBe(false); // no mod
    expect(SAFE_ASSIGNABLE.isWithinRange("shift+e")).toBe(false); // no mod
  });

  it("the modifier is ⌘ (mod) — no new modifier scheme", () => {
    expect(SAFE_ASSIGNABLE.modifier).toBe("mod");
  });
});

describe("detectConflict + precedence", () => {
  it("BLOCKS a custom binding that shadows a built-in (custom-vs-builtin)", () => {
    const c = detectConflict("mod+k", []);
    expect(c).not.toBeNull();
    expect(c!.kind).toBe("builtin");
    expect(isBlockingConflict(c)).toBe(true);
  });

  it("BLOCKS a custom binding that shadows a product combo", () => {
    // "mod+e" is the Read product binding.
    const c = detectConflict("mod+e", []);
    expect(c).not.toBeNull();
    expect(c!.kind).toBe("product");
    expect(isBlockingConflict(c)).toBe(true);
  });

  it("BLOCKS a custom binding that shadows a sub-action combo", () => {
    // "mod+g" is the Research-home sub-action.
    const c = detectConflict("mod+g", []);
    expect(c).not.toBeNull();
    expect(c!.kind).toBe("subaction");
    expect(isBlockingConflict(c)).toBe(true);
  });

  it("BLOCKS a reserved browser combo", () => {
    const c = detectConflict("mod+t", []);
    expect(c!.kind).toBe("reserved");
    expect(isBlockingConflict(c)).toBe(true);
  });

  it("treats custom-vs-custom as OVERRIDABLE (not blocking)", () => {
    const existing = [{ id: "a", spec: "alt+j" }];
    const c = detectConflict("alt+j", existing, "b");
    expect(c).not.toBeNull();
    expect(c!.kind).toBe("custom");
    expect(c!.withId).toBe("a");
    expect(isBlockingConflict(c)).toBe(false);
  });

  it("does not conflict with itself (selfId excluded)", () => {
    const existing = [{ id: "a", spec: "alt+j" }];
    expect(detectConflict("alt+j", existing, "a")).toBeNull();
  });

  it("allows a free safe combo", () => {
    expect(detectConflict("alt+j", [])).toBeNull();
  });
});

describe("binding tables", () => {
  it("has the load-bearing built-ins", () => {
    const ids = BUILTIN_BINDINGS.map((b) => b.id);
    expect(ids).toContain("palette");
    expect(ids).toContain("help");
    expect(ids).toContain("aisidecar");
  });

  it("has NO chord built-in left (the go-* chord rows are gone)", () => {
    const ids = BUILTIN_BINDINGS.map((b) => b.id);
    expect(ids).not.toContain("go-research");
    expect(ids).not.toContain("go-wrestle");
    expect(ids).not.toContain("go-notebooks");
    expect(ids).not.toContain("go-home");
    // And no built-in carries a "Go to (chords)" group.
    expect(BUILTIN_BINDINGS.some((b) => /chord/i.test(b.group))).toBe(false);
  });

  it("every product is reachable by a unique, non-reserved, single ⌘+key combo", () => {
    const specs = new Set<string>();
    for (const p of PRODUCT_BINDINGS) {
      const n = normalizeBinding(p.spec);
      expect(reservedReason(n), `${p.id} (${n}) must not be reserved`).toBeNull();
      expect(isChord(n), `${p.id} must be a combo, not a chord`).toBe(false);
      expect(n.includes("+"), `${p.id} must be a ⌘ combo`).toBe(true);
      specs.add(n);
    }
    expect(specs.size).toBe(PRODUCT_BINDINGS.length); // all unique
  });

  it("fixed bindings contain NO internal duplicate specs (every key is unique)", () => {
    const seen = new Map<string, number>();
    for (const b of fixedBindings()) {
      const n = normalizeBinding(b.spec);
      seen.set(n, (seen.get(n) ?? 0) + 1);
    }
    for (const [spec, count] of seen) {
      expect(count, `${spec} is bound more than once`).toBe(1);
    }
  });

  it("bindingForProduct resolves product + sub-action rows", () => {
    expect(bindingForProduct("read")?.spec).toBe("mod+e");
    expect(bindingForProduct("research")?.spec).toBe("mod+j");
    expect(bindingForProduct("research", "new")?.spec).toBe("mod+g");
  });
});

describe("chipBindings() — the map SPR-07 consumes", () => {
  it("returns one entry per product + sub-action, each a single ⌘ combo with a label + ariaLabel", () => {
    const chips = chipBindings();
    expect(chips.length).toBe(PRODUCT_BINDINGS.length + SUBACTION_BINDINGS.length);
    for (const c of chips) {
      expect(c.id).toBeTruthy();
      expect(c.label).toBeTruthy();
      expect(c.productId).toBeTruthy();
      expect(isChord(c.spec), `${c.id} chip must be a combo`).toBe(false);
      expect(c.spec.includes("+"), `${c.id} chip must be a ⌘ combo`).toBe(true);
      expect(c.ariaLabel, `${c.id} chip must carry an ariaLabel`).toBeTruthy();
    }
  });

  it("the Read chip is exactly what SPR-07 places on the Read door", () => {
    const read = chipBindings().find((c) => c.productId === "read" && !c.actionId);
    expect(read?.spec).toBe("mod+e");
    expect(read?.label).toBe("Read");
    // ariaLabel is the spoken form; mod → Meta-on-mac / Control-elsewhere.
    expect(read?.ariaLabel).toMatch(/^(Meta|Control)\+E$/);
    expect(read?.route).toBe("/library");
  });

  it("the More chip carries NO route (it opens the launcher)", () => {
    const more = chipBindings().find((c) => c.productId === "more");
    // ⌘I, not ⌘M: ⌘M shadows macOS minimize-window (reserved), so More takes
    // the free safe letter ⌘I ("Index of all products").
    expect(more?.spec).toBe("mod+i");
    expect(more?.route).toBeUndefined();
  });
});

describe("route + label honesty (SPR-08)", () => {
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

describe("glyphForToken named-key glyphs (no dead ternary)", () => {
  it("renders named multi-char keys as short glyphs, not shouty all-caps words", () => {
    expect(formatBinding("mod+enter")).toContain("↵");
    expect(formatBinding("mod+enter")).not.toContain("ENTER");
    expect(formatBinding("alt+arrowup")).toContain("↑");
    expect(formatBinding("alt+escape")).toContain("Esc");
    expect(formatBinding("alt+escape")).not.toContain("ESCAPE");
  });

  it("still upper-cases single printable keys", () => {
    expect(formatBinding("mod+r")).toContain("R");
  });
});
