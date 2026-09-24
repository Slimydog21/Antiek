/**
 * z-literal guard (audit M7): a layer that floats over the app reads its
 * z-index from the ladder (zIndex.ts == tokens.css --z-* == the Tailwind
 * keys z-modal, z-popover, z-toast, z-mascot, z-tooltip…), never a number
 * typed at the call site. Before wave 2, LemonDropdown and LemonSelect opened
 * at z-50 (below the modal they could sit in; the ladder's popover rung is
 * 120), the CommandPalette scrim was z-50 and MascotStation z-[60].
 *
 * Scope: class strings (not comments) with a literal z of 50 or more — the
 * global overlay band. Small local stacking (a sticky header's z-10, a resize
 * handle's z-20) is a component's own business and is not flagged.
 * Each remaining literal is owned by another open change; the list can only
 * shrink.
 */
import ts from "typescript";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(import.meta.dirname, "..");

const OWNED_ELSEWHERE: Record<string, string> = {
  "components/ad/AdBorder.tsx z-[150]": "the ad slot, rewritten by design wave 3 (z-ad-overlay once it lands)",
  "modes/Notebook/SlashMenu.tsx z-[120]": "wave 3 rewrote this line (z-popover once it lands)",
};

function files(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...files(p));
    else if (/\.tsx?$/.test(e.name) && !/\.(test|stories)\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

const LITERAL = /(?:^|[\s"'`:])(z-(?:\[(\d+)\]|(\d+)))(?=[\s"'`]|$)/g;

function scan(): string[] {
  const hits: string[] = [];
  for (const file of files(SRC)) {
    const src = readFileSync(file, "utf8");
    if (!/z-(\[|\d)/.test(src)) continue;
    const rel = relative(SRC, file);
    const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    const visit = (n: ts.Node) => {
      if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n)) {
        for (const m of n.getText(sf).matchAll(LITERAL)) {
          const value = Number(m[2] ?? m[3]);
          if (value >= 50) hits.push(`${rel} ${m[1]}`);
        }
        return;
      }
      ts.forEachChild(n, visit);
    };
    visit(sf);
  }
  return hits;
}

describe("z-literal guard — overlays read the ladder", () => {
  const hits = scan();

  it("no class string types a global-band z-index (>= 50) outside the owned-elsewhere list", () => {
    expect(hits.filter((h) => !(h in OWNED_ELSEWHERE))).toEqual([]);
  });

  it("the owned-elsewhere list only names literals that still exist (it can only shrink)", () => {
    for (const k of Object.keys(OWNED_ELSEWHERE)) expect(hits, k).toContain(k);
  });

  it("the guard bites on a typed overlay z", () => {
    expect([..."fixed inset-0 z-[100] flex".matchAll(LITERAL)].map((m) => m[1])).toEqual(["z-[100]"]);
    expect([..."absolute z-50 mt-1".matchAll(LITERAL)].map((m) => m[1])).toEqual(["z-50"]);
  });
});
