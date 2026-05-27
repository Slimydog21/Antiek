/**
 * composition.test.ts — SPR-03: the facet engine's composition guarantees.
 *
 * The SPR-02 byte-equivalence half lives in MasterMdViewer.test.tsx (the DOM
 * render). This file proves the SPR-03 ENGINE properties in isolation (no DOM):
 *
 *   - M5 — the first TWO-augmentation composition: servability + IP-holder both
 *     declare decorations on ONE source range; the facet merges them; both the
 *     verdict class AND the owner name appear on one combined decoration;
 *     NEITHER augmentation imports the other (proved structurally below);
 *   - rigor #3 — ORDER-INDEPENDENCE: shuffling the enable order yields a
 *     byte-identical resolved set (the property the whole facet model rests on);
 *   - M2 — widget decorations: an affordance declared alongside a range resolves
 *     into the combined `widgets` set, de-duplicated + sorted, order-independent;
 *   - M2 — z-order: the decorations facet's priority is fixed by the surface,
 *     not by declaration order;
 *   - M3 — lifecycle: enabling/disabling adds/removes EXACTLY one augmentation's
 *     contributions, with no residue.
 */
import { describe, expect, it } from "vitest";

import type { Anchor, ChunkId, Decoration, ReadingContext } from "./types";
import { anchorKey, combineDecorations, decorationsFacet } from "./facets/decorations";
import {
  RESTRICTED_CLASS,
  SERVABLE_CLASS,
  makeServabilityAugmentation,
} from "./augmentations/servability";
import { makeIpHolderAugmentation } from "./augmentations/ip-holder";
import {
  EnabledAugmentations,
  collectDecorations,
  resolveEnabled,
} from "./registry";

function chunkAnchor(id: string): Anchor {
  return { kind: "chunk", chunkId: id as ChunkId };
}

const STUB_CTX: ReadingContext = {
  synthesis: { question: null, claims: [] },
  layout: { resolve: () => null },
  substrate: {
    getChunk: () => Promise.reject(new Error("not wired in the engine test")),
  },
};

// ── M5 — the first two-augmentation composition ────────────────────────────

describe("composition — servability + IP-holder merge through the facet (M5)", () => {
  it("merges the verdict class AND the owner name onto ONE source range", () => {
    // One source: servable, owned by MIT Press. The two augmentations decorate
    // the SAME representative chunk; the facet combines them.
    const servability = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: true },
    ]);
    const ipHolder = makeIpHolderAugmentation([
      { representativeChunkId: "c1", ipHolderName: "MIT Press" },
    ]);

    const out = collectDecorations([servability, ipHolder], STUB_CTX);

    // ONE resolved decoration (same range) carrying BOTH contributions.
    expect(out).toHaveLength(1);
    const d = out[0];
    expect(d.key).toBe(anchorKey(chunkAnchor("c1")));
    // servability's verdict class is present …
    expect(d.classNames).toContain(SERVABLE_CLASS);
    // … AND the IP-holder's owner name is present, on the same decoration.
    expect(d.ipHolderNames).toEqual(["MIT Press"]);
  });

  it("a restricted source keeps its verdict; a null owner contributes no attribution", () => {
    // §9.0: a non-servable source's owner is withheld (null), so the IP-holder
    // augmentation declares NOTHING for it — no fabricated/leaked attribution.
    const servability = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: false },
    ]);
    const ipHolder = makeIpHolderAugmentation([
      { representativeChunkId: "c1", ipHolderName: null },
    ]);

    const out = collectDecorations([servability, ipHolder], STUB_CTX);
    expect(out).toHaveLength(1);
    expect(out[0].classNames).toEqual([RESTRICTED_CLASS]);
    // No owner leaked onto the restricted branch.
    expect(out[0].ipHolderNames).toEqual([]);
  });

  it("NEITHER augmentation imports the other (PR-3) — proved by their module text", async () => {
    // A structural assertion of PR-3: the composing augmentations meet only at
    // the facet, never via an import. Read each module's source and assert it
    // does not import the other augmentation. (The CI guard enforces this on
    // the whole tree; this test pins it for the M5 pair specifically.)
    const fs = await import("node:fs/promises");
    // vitest runs with cwd = apps/reading, so resolve from the project root.
    const dir = "src/reading-physics/augmentations";
    const serv = await fs.readFile(`${dir}/servability.ts`, "utf8");
    const ip = await fs.readFile(`${dir}/ip-holder.ts`, "utf8");
    expect(serv).not.toMatch(/from\s+["'].*ip-holder["']/);
    expect(ip).not.toMatch(/from\s+["'].*servability["']/);
  });
});

// ── rigor #3 — order independence ──────────────────────────────────────────

describe("order independence — shuffled enable order is byte-identical (rigor #3)", () => {
  it("two augmentations: forward and reverse enable order resolve identically", () => {
    const servability = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: true },
      { representativeChunkId: "c2", servable: false },
    ]);
    const ipHolder = makeIpHolderAugmentation([
      { representativeChunkId: "c1", ipHolderName: "MIT Press" },
      { representativeChunkId: "c2", ipHolderName: null },
    ]);

    const forward = collectDecorations([servability, ipHolder], STUB_CTX);
    const reverse = collectDecorations([ipHolder, servability], STUB_CTX);
    expect(reverse).toEqual(forward);
  });

  it("the EnabledAugmentations set resolves identically regardless of enable order", () => {
    const servability = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: true },
    ]);
    const ipHolder = makeIpHolderAugmentation([
      { representativeChunkId: "c1", ipHolderName: "MIT Press" },
    ]);

    // Enable in one order …
    const a = new EnabledAugmentations().enable(servability).enable(ipHolder);
    // … and the opposite order.
    const b = new EnabledAugmentations().enable(ipHolder).enable(servability);
    expect(resolveEnabled(b, STUB_CTX)).toEqual(resolveEnabled(a, STUB_CTX));
  });

  it("every permutation of three decorations on one range is identical (combine-level)", () => {
    const ds: Decoration[] = [
      { anchor: chunkAnchor("c1"), className: "gamma", title: "G" },
      { anchor: chunkAnchor("c1"), className: "alpha", title: "A" },
      { anchor: chunkAnchor("c1"), className: "beta", title: "B" },
    ];
    const permutations: Decoration[][] = [
      [ds[0], ds[1], ds[2]],
      [ds[0], ds[2], ds[1]],
      [ds[1], ds[0], ds[2]],
      [ds[1], ds[2], ds[0]],
      [ds[2], ds[0], ds[1]],
      [ds[2], ds[1], ds[0]],
    ];
    const baseline = combineDecorations(permutations[0]);
    for (const perm of permutations) {
      expect(combineDecorations(perm)).toEqual(baseline);
    }
    expect(baseline[0].classNames).toEqual(["alpha", "beta", "gamma"]);
    expect(baseline[0].title).toBe("A · B · G");
  });
});

// ── M2 — widget decorations + z-order ──────────────────────────────────────

describe("widget decorations + z-order (M2)", () => {
  it("a widget affordance declared alongside a range resolves into widgets[]", () => {
    const out = combineDecorations([
      {
        anchor: chunkAnchor("c1"),
        className: "highlight",
        widget: { kind: "quote-leap", label: "Leap to source" },
      },
    ]);
    expect(out[0].classNames).toEqual(["highlight"]);
    expect(out[0].widgets).toEqual([{ kind: "quote-leap", label: "Leap to source" }]);
  });

  it("a decoration with NO widget resolves to an empty widgets set (byte-equivalence)", () => {
    const out = combineDecorations([{ anchor: chunkAnchor("c1"), className: "x" }]);
    expect(out[0].widgets).toEqual([]);
  });

  it("widgets on the same range de-duplicate and SORT (order-independent)", () => {
    const forward = combineDecorations([
      { anchor: chunkAnchor("c1"), className: "x", widget: { kind: "quote-leap", label: "Z label" } },
      { anchor: chunkAnchor("c1"), className: "x", widget: { kind: "preview", label: "A label" } },
      // exact duplicate of the first — de-duplicated to one.
      { anchor: chunkAnchor("c1"), className: "x", widget: { kind: "quote-leap", label: "Z label" } },
    ]);
    const reverse = combineDecorations([
      { anchor: chunkAnchor("c1"), className: "x", widget: { kind: "quote-leap", label: "Z label" } },
      { anchor: chunkAnchor("c1"), className: "x", widget: { kind: "preview", label: "A label" } },
    ]);
    // Sorted by (kind,label) key: "preview A label" < "quote-leap Z label".
    expect(forward[0].widgets).toEqual([
      { kind: "preview", label: "A label" },
      { kind: "quote-leap", label: "Z label" },
    ]);
    expect(reverse[0].widgets).toEqual(forward[0].widgets);
  });

  it("the decorations facet exposes a surface-fixed z-order priority", () => {
    // Z-order is a property of the FACET, not of any declaration. The base
    // decorations layer sits at priority 0 (under SPR-04's gutter widgets).
    expect(decorationsFacet.name).toBe("decorations");
    expect(decorationsFacet.priority).toBe(0);
  });
});

// ── M3 — augmentation lifecycle (enable/disable, no residue) ────────────────

describe("augmentation lifecycle — add/remove exactly its contributions (M3)", () => {
  it("disabling an augmentation removes EXACTLY its contributions, no residue", () => {
    const servability = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: true },
    ]);
    const ipHolder = makeIpHolderAugmentation([
      { representativeChunkId: "c1", ipHolderName: "MIT Press" },
    ]);

    const both = new EnabledAugmentations().enable(servability).enable(ipHolder);
    const withBoth = resolveEnabled(both, STUB_CTX);
    expect(withBoth[0].classNames).toContain(SERVABLE_CLASS);
    expect(withBoth[0].ipHolderNames).toEqual(["MIT Press"]);

    // Disable IP-holder: the verdict class survives, the owner name is GONE …
    const servOnly = resolveEnabled(both.disable("ip-holder"), STUB_CTX);
    expect(servOnly[0].classNames).toContain(SERVABLE_CLASS);
    expect(servOnly[0].ipHolderNames).toEqual([]);

    // … and the result is identical to never having enabled IP-holder (no
    // residue from the enable/disable cycle).
    const neverHad = resolveEnabled(
      new EnabledAugmentations().enable(servability),
      STUB_CTX,
    );
    expect(servOnly).toEqual(neverHad);
  });

  it("disabling EVERY augmentation resolves to [] (a clean empty surface)", () => {
    const servability = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: true },
    ]);
    const set = new EnabledAugmentations().enable(servability);
    expect(resolveEnabled(set.disable("servability"), STUB_CTX)).toEqual([]);
  });

  it("enable is idempotent; disable of an absent id is a no-op", () => {
    const servability = makeServabilityAugmentation([
      { representativeChunkId: "c1", servable: true },
    ]);
    const once = new EnabledAugmentations().enable(servability);
    const twice = once.enable(servability);
    expect(resolveEnabled(twice, STUB_CTX)).toEqual(resolveEnabled(once, STUB_CTX));
    expect(once.disable("does-not-exist")).toBe(once);
  });
});
