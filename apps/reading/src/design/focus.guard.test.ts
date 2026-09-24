/**
 * Focus guard — element-level (design spec §4, audit M2).
 *
 * The one focus ring is the global `:focus-visible` rule in src/index.css:
 * 2px in --focus (ink by day, sun at night, >= 3:1 on every ground). Two
 * things can still hide it, and this guard reads every class string in the
 * app, element by element, for both:
 *
 *   1. `outline-none` (bare or `focus:`) with no replacement ring on the
 *      same element. The old guard checked FILES: a file that contained
 *      `focus-visible:ring` anywhere passed, so the spend-ceiling input in
 *      CascadeProposal.tsx had no indicator while the guard stayed green
 *      (replayed: 104 files, 0 violations).
 *   2. A focus ring drawn in the sun (`focus:ring-sun`, `focus-visible:
 *      outline-sun`, `focus:border-sun`): 1.36:1 on the day card, 1.26:1 on
 *      the page, below the 3:1 a focus indicator needs. Use `-focus`.
 *
 * Exempt by construction: an element with tabIndex -1 (a programmatic focus
 * target such as a dialog or a region, never reached by Tab). Everything
 * else that opts out is listed below with its reason, and the list can only
 * shrink.
 */
import ts from "typescript";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(import.meta.dirname, "..");

/** Elements whose indicator is drawn by something the scan cannot see. */
const ALLOW: Record<string, string> = {
  // The label around the borderless input draws the ring (focus-within).
  "components/lemon/LemonInput.tsx": "focus-within:outline-focus on the wrapping label",
  // A full document canvas (TipTap): the caret marks focus; a 2px frame
  // around the page while typing is noise. The prose wave owns this file.
  "modes/Notebook/Editor.tsx": "document canvas; the caret is the indicator",
};

/**
 * modes/Sources/** is owned by open PR #3416; its rings migrate when that
 * lands. Pinned so the count can only go down.
 */
const SOURCES_BASELINE = { outlineNone: 0, sunRing: 11 };

function files(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...files(p));
    else if (/\.tsx?$/.test(e.name) && !/\.(test|stories)\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

type Hit = { file: string; line: number; text: string };

const OUTLINE_NONE = /(^|[\s"'`])(focus:)?outline-none(?=[\s"'`]|$)/;
const REPLACEMENT = /(focus|focus-visible):ring-(\d|focus)|focus-visible:outline(-\d|-focus|-offset|(?=[\s"'`]|$))/;
const SUN_RING = /(focus|focus-visible|focus-within):(ring|outline|border)-sun(?![\w-])/g;

function scan() {
  const outlineNone: Hit[] = [];
  const sunRing: Hit[] = [];
  for (const file of files(SRC)) {
    const src = readFileSync(file, "utf8");
    if (!src.includes("outline-none") && !src.includes("-sun")) continue;
    const rel = relative(SRC, file);
    const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    const visit = (n: ts.Node) => {
      if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n)) {
        const text = n.getText(sf);
        const line = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
        // The class context: the whole attribute / property / declaration the
        // literal belongs to, so a class string split across lines is one unit.
        let ctx: ts.Node = n;
        for (let p = n.parent; p; p = p.parent) {
          if (ts.isJsxAttribute(p) || ts.isPropertyAssignment(p) || ts.isVariableDeclaration(p) || ts.isReturnStatement(p)) {
            ctx = p;
            break;
          }
        }
        const ctxText = ctx.getText(sf);
        for (const m of text.matchAll(SUN_RING)) sunRing.push({ file: rel, line, text: m[0] });
        if (OUTLINE_NONE.test(text) && !REPLACEMENT.test(ctxText)) {
          // A programmatic focus target (tabIndex -1) is never reached by Tab.
          let el: ts.Node | undefined = n;
          while (el && !ts.isJsxOpeningElement(el) && !ts.isJsxSelfClosingElement(el)) el = el.parent;
          const tabIndex = el && (el as ts.JsxOpeningElement).attributes.properties.find(
            (a) => ts.isJsxAttribute(a) && a.name.getText(sf) === "tabIndex",
          );
          const programmatic = tabIndex && /-1/.test(tabIndex.getText(sf));
          if (!programmatic && !ALLOW[rel]) outlineNone.push({ file: rel, line, text: text.slice(0, 80) });
        }
        return;
      }
      ts.forEachChild(n, visit);
    };
    visit(sf);
  }
  return { outlineNone, sunRing };
}

const found = scan();
const inSources = (h: Hit) => h.file.startsWith("modes/Sources/");
const fmt = (hs: Hit[]) => hs.map((h) => `${h.file}:${h.line} ${h.text}`);

describe("focus guard — element-level", () => {
  it("no element hides the focus ring without drawing a replacement", () => {
    expect(fmt(found.outlineNone.filter((h) => !inSources(h)))).toEqual([]);
    expect(found.outlineNone.filter(inSources).length).toBeLessThanOrEqual(SOURCES_BASELINE.outlineNone);
  });

  it("no focus ring is drawn in the sun (1.36:1 on the day card)", () => {
    expect(fmt(found.sunRing.filter((h) => !inSources(h)))).toEqual([]);
    expect(found.sunRing.filter(inSources).length).toBeLessThanOrEqual(SOURCES_BASELINE.sunRing);
  });

  it("every allowlisted file still draws its indicator the way its reason says", () => {
    const input = readFileSync(join(SRC, "components/lemon/LemonInput.tsx"), "utf8");
    expect(input).toMatch(/focus-within:outline-focus/);
    for (const f of Object.keys(ALLOW)) expect(() => readFileSync(join(SRC, f))).not.toThrow();
  });

  it("the guard bites: it flags a bare outline-none and a sun ring", () => {
    const probe = ts.createSourceFile("p.tsx", 'const a = <input className="px-2 outline-none" />; const b = "focus:ring-2 focus:ring-sun";', ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const lits: string[] = [];
    const walk = (n: ts.Node) => { if (ts.isStringLiteral(n)) lits.push(n.text); ts.forEachChild(n, walk); };
    walk(probe);
    expect(lits.some((t) => OUTLINE_NONE.test(t) && !REPLACEMENT.test(t))).toBe(true);
    expect(lits.some((t) => [...t.matchAll(SUN_RING)].length > 0)).toBe(true);
  });
});
