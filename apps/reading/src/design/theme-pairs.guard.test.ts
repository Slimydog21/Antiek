/**
 * theme-pairs guard: no colour pair a component draws may read in one theme
 * and fail in the other.
 *
 * WHY: the semantic layer made surfaces follow the theme (bg-ice-1 is the
 * night card at night) while pigments stay put (text-ink is ink in both
 * themes, fill-ice-0 was meant to stay paper). A following colour paired with
 * a fixed one is legible in one theme and gone in the other: the outline
 * shelf's blocks drew ink on the night card at 1.13:1, and the brand mark on
 * the dock's Home key filled its lobes with the night card under ink folds,
 * also 1.13:1. Neither view has a story, so axe never saw them, and
 * tokens.contrast.test.ts checks what the tokens offer, not what call sites
 * pair. This guard reads the pairs call sites actually write.
 *
 * HOW: every JSX className in src (tests and stories aside) is resolved in
 * BOTH themes through the real tailwind.config.js and tokens.css (the parser
 * the other token gates use, tokenCss.ts): the text colour against the ground
 * beneath it (the element's own bg, else the nearest JSX ancestor's, with
 * /opacity washes composited over what lies under them), and an SVG stroke
 * against its own fill. A pair that clears its bar in one theme (AA 4.5:1 for
 * text, 3:1 for a drawn mark) and misses it in the other fails.
 *
 * WHAT IT SKIPS, on purpose: pairs that fail in BOTH themes (a bad pairing,
 * not a theme mismatch: axe owns those), an element whose className holds two
 * candidate colours (a conditional it cannot evaluate), a ground painted by an
 * arbitrary value, aria-hidden decoration, and any ground a parent COMPONENT
 * paints: it follows JSX nesting, not renders, so FloatMenu's panels, which
 * sit on its ink island as separate components, are outside its sight.
 *
 * PROOF IT BITES: point it at another tree and it reports that tree's pairs.
 *   TOKENS_CSS=<path> TAILWIND_CONFIG=<path> PAIRS_SRC=<dir> npx vitest run src/design/theme-pairs.guard.test.ts
 * At the merge base (2c35367ce, before the semantic layer) it reports 415
 * one-sided pairs, most of them dark:text-moonlight at 3.50 on the night card.
 * On the wave's first cut (12fac9a10) it failed on four pairs: the shelf
 * label (night 1.13), the BrainMark folds (night 1.13), AccountMemory's error
 * line (text-emperor on bg-red-50, night 2.71) and FloatMenu's Hybrid note
 * (text-sun-deep on the ink island, day 3.09).
 */
import { readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import resolveConfig from "tailwindcss/resolveConfig";
import ts from "typescript";
import { describe, expect, it } from "vitest";

import { contrastRatio, over, type Rgb } from "../../e2e/_ams/visible";
import { parseTokensCss, resolveTailwindColor, type Rgba, type ThemeName } from "./tokenCss";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..");
const SRC = process.env.PAIRS_SRC ? resolve(process.env.PAIRS_SRC) : join(APP, "src");
const cssPath = process.env.TOKENS_CSS ? resolve(process.env.TOKENS_CSS) : join(here, "tokens.css");
const twPath = process.env.TAILWIND_CONFIG ? resolve(process.env.TAILWIND_CONFIG) : join(APP, "tailwind.config.js");

const sheet = parseTokensCss(readFileSync(cssPath, "utf8"));
const twModule = createRequire(import.meta.url)(twPath);
const theme = resolveConfig(twModule.default ?? twModule).theme as unknown as Record<string, Record<string, unknown>>;

type Kind = "text" | "bg" | "fill" | "stroke";
/** Flatten a resolved colour map to utility keys: {teal: {DEFAULT, 500}} → teal, teal-500. */
function flatten(obj: Record<string, unknown>, prefix = "", out = new Map<string, string>()): Map<string, string> {
  for (const [k, v] of Object.entries(obj ?? {})) {
    const key = k === "DEFAULT" ? prefix : prefix ? `${prefix}-${k}` : k;
    if (v && typeof v === "object") flatten(v as Record<string, unknown>, key, out);
    else if (typeof v === "string") out.set(key, v);
  }
  return out;
}
const COLORS: Record<Kind, Map<string, string>> = {
  text: flatten(theme.textColor),
  bg: flatten(theme.backgroundColor),
  fill: flatten(theme.fill),
  stroke: flatten(theme.stroke),
};

const THEMES: ThemeName[] = ["light", "dark"];
const BAR = { text: 4.5, mark: 3 } as const; // WCAG 1.4.3 / 1.4.11

type Tok = { kind: Kind; key: string; alpha: number; night: boolean };
/** A className's colour utilities. Base and `dark:` only; hover:, focus: etc. are states, not the resting pair. */
function colourTokens(classes: string[]): { toks: Tok[]; opaqueUnknownGround: boolean } {
  const toks: Tok[] = [];
  let opaqueUnknownGround = false;
  for (const raw of classes) {
    const parts = raw.split(":");
    const util = parts.pop()!;
    const variants = parts.filter((v) => !/^(sm|md|lg|xl|2xl)$/.test(v));
    const night = variants.length === 1 && variants[0] === "dark";
    if (variants.length && !night) continue;
    const m = util.match(/^(text|bg|fill|stroke)-(.+?)(?:\/(\d+))?$/);
    if (!m) continue;
    const kind = m[1] as Kind;
    if (!COLORS[kind].has(m[2])) {
      // bg-[#123] / bg-[url()] / bg-gradient-to-r paint a ground this guard cannot read.
      if (kind === "bg" && /^(\[|gradient)/.test(m[2])) opaqueUnknownGround = true;
      continue;
    }
    toks.push({ kind, key: m[2], alpha: m[3] ? Number(m[3]) / 100 : 1, night });
  }
  return { toks, opaqueUnknownGround };
}

/** The tokens of `kind` in force for a theme: at night a dark: token wins. */
function inForce(toks: Tok[], kind: Kind, t: ThemeName): Tok[] {
  const night = toks.filter((x) => x.kind === kind && x.night);
  return t === "dark" && night.length ? night : toks.filter((x) => x.kind === kind && !x.night);
}

function colour(t: ThemeName, tok: Tok): Rgba | null {
  const c = resolveTailwindColor(sheet, t, COLORS[tok.kind].get(tok.key)!);
  return c ? { ...c, a: c.a * tok.alpha } : null;
}
const name = (tok: Tok) => `${tok.night ? "dark:" : ""}${tok.kind}-${tok.key}${tok.alpha < 1 ? `/${Math.round(tok.alpha * 100)}` : ""}`;
const onto = (top: Rgba, under: Rgb): Rgb => (top.a < 1 ? over(top, under) : top);

/** Every string fragment inside a className={…} expression (branches included). */
function classStrings(attr: ts.JsxAttribute): string[] {
  const out: string[] = [];
  const visit = (n: ts.Node) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) {
      out.push(...n.text.split(/\s+/).filter(Boolean));
    }
    n.forEachChild(visit);
  };
  if (attr.initializer) visit(attr.initializer);
  return out;
}

type Layer = { toks: Tok[]; unknown: boolean };
type Finding = { where: string; pair: string; theme: ThemeName; ratio: number; other: number };

/**
 * The opaque ground under the innermost layer, per theme: the nearest opaque
 * bg with every translucent wash above it composited on. null = undecidable.
 */
function ground(stack: Layer[], t: ThemeName): { rgb: Rgb; label: string } | null {
  let i = stack.length - 1;
  const washes: Tok[] = [];
  for (; i >= 0; i--) {
    if (stack[i].unknown) return null;
    const bgs = inForce(stack[i].toks, "bg", t);
    if (bgs.length > 1) return null;
    if (!bgs.length) continue;
    const c = colour(t, bgs[0]);
    if (!c) return null;
    washes.unshift(bgs[0]);
    if (c.a >= 1) break;
  }
  if (i < 0) return null; // no opaque ground in this file
  let rgb: Rgb = colour(t, washes[0])!;
  for (const w of washes.slice(1)) rgb = onto(colour(t, w)!, rgb);
  return { rgb, label: washes.map(name).join(" > ") };
}

/** The one-sided pairs in one TSX source. */
function scanSource(label: string, source: string): Finding[] {
  const findings: Finding[] = [];
  {
    const sf = ts.createSourceFile(label, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const where = (n: ts.Node) => `${label}:${sf.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
    const oneSided = (n: ts.Node, pair: (t: ThemeName) => { ratio: number; label: string } | null, bar: number) => {
      const r = THEMES.map(pair);
      if (!r[0] || !r[1]) return;
      const [lo, hi] = r[0].ratio <= r[1].ratio ? [0, 1] : [1, 0];
      if (r[lo]!.ratio < bar && r[hi]!.ratio >= bar) {
        findings.push({ where: where(n), pair: r[lo]!.label, theme: THEMES[lo], ratio: r[lo]!.ratio, other: r[hi]!.ratio });
      }
    };

    const visit = (n: ts.Node, stack: Layer[]) => {
      if (!ts.isJsxElement(n) && !ts.isJsxSelfClosingElement(n)) {
        n.forEachChild((c) => visit(c, stack));
        return;
      }
      const open = ts.isJsxElement(n) ? n.openingElement : n;
      const attrs = open.attributes.properties.filter(ts.isJsxAttribute);
      const attr = (a: string) => attrs.find((p) => p.name.getText() === a);
      const cls = attr("className");
      const { toks, opaqueUnknownGround } = cls ? colourTokens(classStrings(cls)) : { toks: [], opaqueUnknownGround: false };
      const styled = /background/i.test(attr("style")?.getText() ?? "");
      const layer: Layer = { toks, unknown: opaqueUnknownGround || styled };
      const next = [...stack, layer];
      const hidden = /^aria-hidden(=\{?\s*(true|"true")\s*\}?)?$/.test(attr("aria-hidden")?.getText() ?? "");

      if (!hidden && toks.some((x) => x.kind === "text")) {
        oneSided(n, (t) => {
          const fg = inForce(toks, "text", t);
          const g = ground(next, t);
          if (fg.length !== 1 || !g) return null;
          const c = colour(t, fg[0]);
          return c && { ratio: contrastRatio(onto(c, g.rgb), g.rgb), label: `${name(fg[0])} on ${g.label}` };
        }, BAR.text);
      }
      if (toks.some((x) => x.kind === "stroke") && toks.some((x) => x.kind === "fill")) {
        oneSided(n, (t) => {
          const [s, f] = [inForce(toks, "stroke", t), inForce(toks, "fill", t)];
          if (s.length !== 1 || f.length !== 1) return null;
          const [sc, fc] = [colour(t, s[0]), colour(t, f[0])];
          return sc && fc && fc.a >= 1 ? { ratio: contrastRatio(onto(sc, fc), fc), label: `${name(s[0])} on ${name(f[0])}` } : null;
        }, BAR.mark);
      }
      if (ts.isJsxElement(n)) n.children.forEach((c) => visit(c, next));
      else n.forEachChild((c) => visit(c, next));
    };
    visit(sf, []);
  }
  return findings;
}

function scan(): Finding[] {
  const files: string[] = [];
  (function walk(dir: string) {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith(".tsx") && !/\.(test|stories)\.tsx$/.test(e.name)) files.push(p);
    }
  })(SRC);
  return files.flatMap((f) => scanSource(relative(SRC, f), readFileSync(f, "utf8")));
}

/**
 * Night pairs that already failed AA on origin/main before the semantic layer
 * (2c35367ce, resolved through that tree's config and tokens; the night ratio
 * there is in brackets). The semantic layer raised most of them but not past
 * 4.5 while their day side passes, so they read as one-sided now. They are
 * moonlight on a sun-tinted wash and ink on a sun wash at night: the views own
 * them, not the tokens. This set only shrinks. Keyed by file and pair, not by
 * line, so edits nearby do not churn it.
 */
const PRE_EXISTING = new Set([
  "components/ChatInput.tsx | dark:text-moonlight on dark:bg-slate-1", // [3.05] now 4.35
  "components/ModelPicker.tsx | dark:text-moonlight on dark:bg-charcoal-1 > dark:bg-sun/10", // [3.08] now 4.39
  "components/ModelPicker.tsx | dark:text-moonlight on dark:bg-charcoal-1 > dark:bg-sun/10 > bg-moonlight/15", // [2.63] now 3.54
  "modes/Multimedia/index.tsx | text-ink on dark:bg-charcoal-2 > bg-sun/10", // [1.44] now 1.44
  "modes/Notebook/SlashMenu.tsx | dark:text-moonlight on dark:bg-charcoal-2 > dark:bg-sun/15", // [2.39] now 3.41
  "modes/Reading/PersonalSpace/index.tsx | dark:text-moonlight on dark:bg-charcoal-2 > bg-sun/10", // [2.75] now 3.92
]);
const keyOf = (f: Finding) => `${f.where.replace(/:\d+$/, "")} | ${f.pair}`;

describe("theme-pairs guard", () => {
  const findings = scan();

  it("no pair a call site draws reads in one theme and fails in the other", () => {
    const fresh = findings
      .filter((f) => !PRE_EXISTING.has(keyOf(f)))
      .map((f) => `${f.where}  ${f.pair}: ${f.theme} ${f.ratio.toFixed(2)} (other theme ${f.other.toFixed(2)})`);
    expect(fresh).toEqual([]);
  });

  it("the pre-existing list only shrinks: every entry still occurs", () => {
    const seen = new Set(findings.map(keyOf));
    expect([...PRE_EXISTING].filter((k) => !seen.has(k))).toEqual([]);
  });

  it("bites: a fixed pigment on a following ground is caught, a dark: pair or a fixed ground clears it", () => {
    const one = (jsx: string) => scanSource("fixture.tsx", `export const F = () => (${jsx});`);
    // ink on the card that turns night (the outline-shelf defect)
    expect(one(`<li className="bg-ice-1"><p className="text-ink">label</p></li>`)).toMatchObject([
      { pair: "text-ink on bg-ice-1", theme: "dark" },
    ]);
    // paper lobes under ink folds, drawn from a key that follows the card (the BrainMark defect)
    expect(one(`<svg><path className="fill-card stroke-ink" /></svg>`)).toMatchObject([
      { pair: "stroke-ink on fill-card", theme: "dark" },
    ]);
    // the fixes: pair the text for night, or keep ink on a ground that does not flip
    expect(one(`<li className="bg-ice-1"><p className="text-ink dark:text-bright">label</p></li>`)).toEqual([]);
    expect(one(`<li className="bg-sun"><p className="text-ink">label</p></li>`)).toEqual([]);
    // what it cannot decide it skips: a conditional ground, decoration
    expect(one(`<li className={on ? "bg-sun" : "bg-ice-1"}><p className="text-ink">label</p></li>`)).toEqual([]);
    expect(one(`<li className="bg-ice-1"><span aria-hidden="true" className="text-ink">x</span></li>`)).toEqual([]);
  });
});
